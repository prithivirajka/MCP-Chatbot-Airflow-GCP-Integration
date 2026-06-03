"""
DAG 3: Streaming simulation
Schedule: Every 5 minutes
Simulates a Kafka-like event stream by generating fake order events and
appending them to DuckDB raw.order_events. Mimics real-time order activity.
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
import duckdb
import os
import random
import uuid
from loguru import logger

DUCKDB_PATH = os.getenv("DUCKDB_PATH", "./data/duckdb/platform.duckdb")

default_args = {
    "owner": "prith",
    "retries": 0,
    "email_on_failure": False,
}

EVENT_TYPES = ["order_placed", "order_approved", "order_shipped", "order_delivered", "order_cancelled"]
SELLER_IDS = [f"seller_{i:03d}" for i in range(1, 51)]
PRODUCT_CATEGORIES = [
    "electronics", "furniture", "clothing", "sports", "toys",
    "health_beauty", "books", "auto", "food", "garden",
]


def generate_order_events(**context):
    """
    Generate 5–20 fake order events per run and append to raw.order_events.
    Each event simulates a message that would come off a Kafka topic.
    """
    con = duckdb.connect(DUCKDB_PATH)
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    con.execute("""
        CREATE TABLE IF NOT EXISTS raw.order_events (
            event_id VARCHAR PRIMARY KEY,
            event_type VARCHAR,
            order_id VARCHAR,
            seller_id VARCHAR,
            customer_state VARCHAR,
            product_category VARCHAR,
            order_value DOUBLE,
            event_ts TIMESTAMP,
            processing_time_ms INTEGER,
            ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    states = ["SP", "RJ", "MG", "RS", "PR", "SC", "BA", "CE", "PE", "GO"]
    n_events = random.randint(5, 20)

    rows = []
    for _ in range(n_events):
        rows.append((
            str(uuid.uuid4()),
            random.choice(EVENT_TYPES),
            str(uuid.uuid4()),
            random.choice(SELLER_IDS),
            random.choice(states),
            random.choice(PRODUCT_CATEGORIES),
            round(random.uniform(20.0, 800.0), 2),
            datetime.utcnow(),
            random.randint(50, 2000),
        ))

    con.executemany("""
        INSERT OR IGNORE INTO raw.order_events
        (event_id, event_type, order_id, seller_id, customer_state,
         product_category, order_value, event_ts, processing_time_ms)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)

    total = con.execute("SELECT COUNT(*) FROM raw.order_events").fetchone()[0]
    con.close()
    logger.info(f"Generated {n_events} events. Total events in table: {total:,}")


with DAG(
    dag_id="dag_03_streaming_simulation",
    default_args=default_args,
    schedule_interval="*/5 * * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["streaming", "simulation", "events"],
    doc_md="""
    ## Streaming Simulation DAG
    Generates synthetic order events every 5 minutes into raw.order_events.
    Simulates a Kafka consumer writing to the data lake.
    Used by the demand forecast endpoint and analyst agent.
    """,
) as dag:

    PythonOperator(
        task_id="generate_order_events",
        python_callable=generate_order_events,
    )
