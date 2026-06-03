"""
Initialize DuckDB database schemas.
Run once before dbt or the API.
"""

import duckdb
import os

DUCKDB_PATH = os.getenv("DUCKDB_PATH", "./data/duckdb/platform.duckdb")


def init_db():
    con = duckdb.connect(DUCKDB_PATH)
    print(f"Initializing DuckDB at: {DUCKDB_PATH}")

    schemas = ["raw", "staging", "marts", "observability"]
    for schema in schemas:
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        print(f"  ✓ Schema created: {schema}")

    # Pre-create observability request_log so the API can write to it immediately
    con.execute("""
        CREATE TABLE IF NOT EXISTS observability.request_log (
            request_id    VARCHAR,
            agent_id      VARCHAR,
            endpoint      VARCHAR,
            method        VARCHAR,
            status_code   INTEGER,
            latency_ms    DOUBLE,
            cache_hit     BOOLEAN,
            logged_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("  ✓ observability.request_log ready")

    con.close()
    print("\nDatabase initialized. Next steps:")
    print("  1. Place Olist CSVs in data/raw/")
    print("  2. Run: cd dbt_project && dbt run")
    print("  3. Run: uvicorn api.main:app --reload")
    print("  4. Run: python agents/run_agents.py")
    print("  5. Run: streamlit run dashboard/app.py")


if __name__ == "__main__":
    init_db()
