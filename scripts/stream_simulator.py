"""
Standalone streaming simulator — runs DAG 3 logic in a loop.
Use this instead of Airflow on Windows during development.
Generates fake order events every 5 minutes into raw.order_events.

Run with: python scripts/stream_simulator.py
Stop with: Ctrl+C
"""

import duckdb
import os
import random
import uuid
import time
from datetime import datetime
from loguru import logger

DUCKDB_PATH = os.getenv("DUCKDB_PATH", "./data/duckdb/platform.duckdb")
INTERVAL_SECONDS = 300  # 5 minutes

EVENT_TYPES  = ["order_placed", "order_approved", "order_shipped", "order_delivered", "order_cancelled"]
CATEGORIES   = ["electronics", "furniture", "clothing", "sports", "toys",
                "health_beauty", "books", "auto", "food", "garden"]
STATES       = ["SP", "RJ", "MG", "RS", "PR", "SC", "BA", "CE", "PE", "GO"]


def generate_events():
    con = duckdb.connect(DUCKDB_PATH)
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    con.execute("""
        CREATE TABLE IF NOT EXISTS raw.order_events (
            event_id VARCHAR,
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

    n = random.randint(5, 20)
    rows = [(
        str(uuid.uuid4()),
        random.choice(EVENT_TYPES),
        str(uuid.uuid4()),
        f"seller_{random.randint(1,50):03d}",
        random.choice(STATES),
        random.choice(CATEGORIES),
        round(random.uniform(20.0, 800.0), 2),
        datetime.utcnow(),
        random.randint(50, 2000),
    ) for _ in range(n)]

    con.executemany("""
        INSERT INTO raw.order_events
        (event_id, event_type, order_id, seller_id, customer_state,
         product_category, order_value, event_ts, processing_time_ms)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)

    total = con.execute("SELECT COUNT(*) FROM raw.order_events").fetchone()[0]
    con.close()
    return n, total


if __name__ == "__main__":
    logger.info(f"Streaming simulator started. Generating events every {INTERVAL_SECONDS}s. Press Ctrl+C to stop.")
    run = 0
    while True:
        run += 1
        n, total = generate_events()
        logger.info(f"Run #{run} | Generated {n} events | Total in table: {total:,}")
        logger.info(f"Next run in {INTERVAL_SECONDS}s...")
        time.sleep(INTERVAL_SECONDS)
