"""
DAG 2: Hourly CSV ingestion
Schedule: Every hour
Source: Olist Brazilian E-Commerce CSV files (data/raw/)
Lands into: DuckDB raw.orders, raw.order_items, raw.sellers, raw.products, raw.customers
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
import duckdb
import os
from pathlib import Path
from loguru import logger

DUCKDB_PATH = os.getenv("DUCKDB_PATH", "./data/duckdb/platform.duckdb")
RAW_DATA_PATH = os.getenv("RAW_DATA_PATH", "./data/raw")

default_args = {
    "owner": "prith",
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
    "email_on_failure": False,
}

# Map of table name → CSV filename (Olist naming convention)
CSV_TABLE_MAP = {
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "products": "olist_products_dataset.csv",
    "customers": "olist_customers_dataset.csv",
    "order_reviews": "olist_order_reviews_dataset.csv",
    "order_payments": "olist_order_payments_dataset.csv",
}


def ingest_csvs(**context):
    """
    Read Olist CSVs from data/raw/ and load into DuckDB raw schema.
    Uses DuckDB's native read_csv_auto — no pandas needed.
    """
    con = duckdb.connect(DUCKDB_PATH)
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")

    loaded = []
    missing = []

    for table_name, csv_file in CSV_TABLE_MAP.items():
        csv_path = Path(RAW_DATA_PATH) / csv_file
        if not csv_path.exists():
            missing.append(csv_file)
            logger.warning(f"CSV not found, skipping: {csv_path}")
            continue

        # Drop and recreate — idempotent full refresh
        con.execute(f"DROP TABLE IF EXISTS raw.{table_name}")
        con.execute(f"""
            CREATE TABLE raw.{table_name} AS
            SELECT *, CURRENT_TIMESTAMP AS ingested_at
            FROM read_csv_auto('{csv_path.as_posix()}', header=True)
        """)
        row_count = con.execute(f"SELECT COUNT(*) FROM raw.{table_name}").fetchone()[0]
        loaded.append((table_name, row_count))
        logger.info(f"Loaded raw.{table_name}: {row_count:,} rows")

    con.close()

    if missing:
        logger.warning(f"Missing CSVs (download from Kaggle): {missing}")
    if not loaded:
        raise FileNotFoundError(
            "No CSVs found in data/raw/. Download the Olist dataset from "
            "https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce"
        )

    # Push stats to XCom for the validation task
    context["ti"].xcom_push(key="loaded_tables", value=loaded)


def validate_row_counts(**context):
    """Fail DAG if any critical table falls below expected minimums."""
    min_rows = {
        "orders": 90_000,
        "order_items": 100_000,
        "sellers": 3_000,
    }
    con = duckdb.connect(DUCKDB_PATH)
    failures = []
    for table, minimum in min_rows.items():
        try:
            count = con.execute(f"SELECT COUNT(*) FROM raw.{table}").fetchone()[0]
            if count < minimum:
                failures.append(f"raw.{table} has {count} rows, expected >= {minimum}")
        except Exception:
            failures.append(f"raw.{table} does not exist")
    con.close()

    if failures:
        raise ValueError(f"Row count validation failed:\n" + "\n".join(failures))
    logger.info("All row count validations passed")


with DAG(
    dag_id="dag_02_hourly_csv_ingestion",
    default_args=default_args,
    schedule_interval="0 * * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["ingestion", "csv", "olist", "hourly"],
    doc_md="""
    ## Hourly CSV Ingestion DAG
    Loads Olist Brazilian E-Commerce CSVs into DuckDB raw schema.
    Full refresh on each run — idempotent by design.
    Place CSV files in data/raw/ before running.
    """,
) as dag:

    t1 = PythonOperator(
        task_id="ingest_olist_csvs",
        python_callable=ingest_csvs,
    )

    t2 = PythonOperator(
        task_id="validate_row_counts",
        python_callable=validate_row_counts,
    )

    t1 >> t2
