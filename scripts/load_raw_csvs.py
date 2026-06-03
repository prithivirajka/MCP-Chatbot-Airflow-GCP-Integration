"""
One-time script to load Olist CSVs into DuckDB raw schema.
Bypasses Airflow for initial setup — same logic as dag_02_hourly_csv_ingestion.py
Run from project root: python scripts/load_raw_csvs.py
"""

import duckdb
import os
from pathlib import Path

DUCKDB_PATH = os.getenv("DUCKDB_PATH", "./data/duckdb/platform.duckdb")
RAW_DATA_PATH = "./data/raw"

CSV_TABLE_MAP = {
    "orders":          "olist_orders_dataset.csv",
    "order_items":     "olist_order_items_dataset.csv",
    "sellers":         "olist_sellers_dataset.csv",
    "products":        "olist_products_dataset.csv",
    "customers":       "olist_customers_dataset.csv",
    "order_reviews":   "olist_order_reviews_dataset.csv",
    "order_payments":  "olist_order_payments_dataset.csv",
}

con = duckdb.connect(DUCKDB_PATH)
con.execute("CREATE SCHEMA IF NOT EXISTS raw")

for table_name, csv_file in CSV_TABLE_MAP.items():
    csv_path = Path(RAW_DATA_PATH) / csv_file
    if not csv_path.exists():
        print(f"  ⚠  MISSING: {csv_file} — skipping")
        continue

    con.execute(f"DROP TABLE IF EXISTS raw.{table_name}")
    con.execute(f"""
        CREATE TABLE raw.{table_name} AS
        SELECT *, CURRENT_TIMESTAMP AS ingested_at
        FROM read_csv_auto('{csv_path.as_posix()}', header=True)
    """)
    count = con.execute(f"SELECT COUNT(*) FROM raw.{table_name}").fetchone()[0]
    print(f"  ✓  raw.{table_name}: {count:,} rows")

# Also seed raw.order_events so mart_demand_forecast has something to build on
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

# Seed with 200 synthetic events so dbt mart builds without errors
import random, uuid
from datetime import datetime, timedelta

random.seed(42)
EVENT_TYPES = ["order_placed", "order_approved", "order_shipped", "order_delivered", "order_cancelled"]
CATEGORIES  = ["electronics", "furniture", "clothing", "sports", "toys",
                "health_beauty", "books", "auto", "food", "garden"]
STATES      = ["SP", "RJ", "MG", "RS", "PR", "SC", "BA", "CE", "PE", "GO"]

rows = []
for i in range(200):
    rows.append((
        str(uuid.uuid4()),
        random.choice(EVENT_TYPES),
        str(uuid.uuid4()),
        f"seller_{random.randint(1,50):03d}",
        random.choice(STATES),
        random.choice(CATEGORIES),
        round(random.uniform(20.0, 800.0), 2),
        datetime.utcnow() - timedelta(hours=random.randint(0, 23)),
        random.randint(50, 2000),
    ))

con.executemany("""
    INSERT INTO raw.order_events
    (event_id, event_type, order_id, seller_id, customer_state,
     product_category, order_value, event_ts, processing_time_ms)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
""", rows)
print(f"  ✓  raw.order_events: 200 seed rows")

con.close()
print("\nAll raw tables loaded. Now run: cd dbt_project && dbt run --profiles-dir .")
