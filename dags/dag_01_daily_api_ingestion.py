"""
DAG 1: Daily API ingestion
Schedule: 6:00 AM daily
Sources: Open-Meteo (weather) + Alpha Vantage (economic indicators — free tier)
Lands into: DuckDB raw.weather_daily, raw.economic_indicators
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
import duckdb
import httpx
import os
import json
from loguru import logger

DUCKDB_PATH = os.getenv("DUCKDB_PATH", "./data/duckdb/platform.duckdb")

default_args = {
    "owner": "prith",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}


def fetch_weather(**context):
    """Fetch daily weather data for São Paulo (Olist's main market)."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": -23.55,
        "longitude": -46.63,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max",
        "timezone": "America/Sao_Paulo",
        "forecast_days": 7,
    }
    resp = httpx.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    logger.info(f"Fetched {len(data['daily']['time'])} days of weather data")

    con = duckdb.connect(DUCKDB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS raw.weather_daily (
            date DATE,
            temp_max DOUBLE,
            temp_min DOUBLE,
            precipitation_mm DOUBLE,
            windspeed_max DOUBLE,
            ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    rows = list(zip(
        data["daily"]["time"],
        data["daily"]["temperature_2m_max"],
        data["daily"]["temperature_2m_min"],
        data["daily"]["precipitation_sum"],
        data["daily"]["windspeed_10m_max"],
    ))
    # Upsert by date
    con.execute("DELETE FROM raw.weather_daily WHERE date >= CURRENT_DATE")
    con.executemany(
        "INSERT INTO raw.weather_daily (date, temp_max, temp_min, precipitation_mm, windspeed_max) VALUES (?, ?, ?, ?, ?)",
        rows
    )
    con.close()
    logger.info(f"Loaded {len(rows)} weather rows into DuckDB")


def validate_weather(**context):
    """Basic data quality check — fail the DAG if rows are missing."""
    con = duckdb.connect(DUCKDB_PATH)
    count = con.execute(
        "SELECT COUNT(*) FROM raw.weather_daily WHERE date >= CURRENT_DATE"
    ).fetchone()[0]
    con.close()
    if count == 0:
        raise ValueError("Weather validation failed: no rows for today")
    logger.info(f"Validation passed: {count} weather rows present")


with DAG(
    dag_id="dag_01_daily_api_ingestion",
    default_args=default_args,
    schedule_interval="0 6 * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["ingestion", "api", "daily"],
    doc_md="""
    ## Daily API Ingestion DAG
    Fetches weather data for São Paulo from Open-Meteo (free, no auth required).
    Lands raw data into DuckDB for dbt to pick up.
    """,
) as dag:

    t1 = PythonOperator(
        task_id="fetch_weather_api",
        python_callable=fetch_weather,
    )

    t2 = PythonOperator(
        task_id="validate_weather_load",
        python_callable=validate_weather,
    )

    t1 >> t2
