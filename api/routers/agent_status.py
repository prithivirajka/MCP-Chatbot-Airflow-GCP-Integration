from fastapi import APIRouter
from fastapi.responses import JSONResponse
import duckdb
import os

router = APIRouter()
DUCKDB_PATH = os.getenv("DUCKDB_PATH", "./data/duckdb/platform.duckdb")


@router.get("/")
def get_agent_status():
    con = duckdb.connect(DUCKDB_PATH, read_only=True)
    marts = {
        "mart_supply_health":      "main_marts.mart_supply_health",
        "mart_seller_performance": "main_marts.mart_seller_performance",
        "mart_demand_forecast":    "main_marts.mart_demand_forecast",
    }
    status = {}
    for name, table in marts.items():
        try:
            row = con.execute(f"""
                SELECT
                    MAX(freshness_ts)       AS last_refreshed,
                    AVG(confidence_score)   AS avg_confidence,
                    COUNT(*)                AS row_count
                FROM {table}
            """).fetchone()
            status[name] = {
                "last_refreshed": str(row[0]),
                "avg_confidence": round(row[1], 3) if row[1] else 0,
                "row_count": row[2],
                "healthy": row[1] is not None and row[1] >= 0.6,
            }
        except Exception as e:
            status[name] = {"error": str(e), "healthy": False}
    con.close()
    return JSONResponse(content={"marts": status})
