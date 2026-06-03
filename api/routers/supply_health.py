from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
import duckdb
import redis
import json
import os

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

DUCKDB_PATH = os.getenv("DUCKDB_PATH", "./data/duckdb/platform.duckdb")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_TTL = int(os.getenv("REDIS_TTL_SECONDS", 600))

redis_client = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)
CACHE_KEY = "supply_health:v1"


@router.get("/")
@limiter.limit("10/minute")
def get_supply_health(request: Request, days: int = 30):
    """
    Returns delivery KPIs for the last N days (default 30).
    Pass days=3000 to get full Olist historical dataset.
    Each row includes freshness_ts and confidence_score for agent consumption.
    """
    cache_key = f"{CACHE_KEY}:days={days}"
    cached = redis_client.get(cache_key)

    if cached:
        response = JSONResponse(content=json.loads(cached))
        response.headers["X-Cache"] = "HIT"
        return response

    # Use a wide window by default to cover historical Olist data (2016-2018)
    date_filter = f"WHERE kpi_date >= CURRENT_DATE - INTERVAL {days} DAY" if days < 3000 else ""

    con = duckdb.connect(DUCKDB_PATH, read_only=True)
    rows = con.execute(f"""
        SELECT
            kpi_date,
            total_orders,
            delivered_orders,
            cancelled_orders,
            ROUND(avg_delivery_days, 2)       AS avg_delivery_days,
            ROUND(on_time_delivery_rate, 4)   AS on_time_delivery_rate,
            CAST(freshness_ts AS VARCHAR)     AS freshness_ts,
            confidence_score,
            data_source
        FROM main_marts.mart_supply_health
        {date_filter}
        ORDER BY kpi_date DESC
        LIMIT 90
    """).fetchdf()
    con.close()

    payload = {
        "data": rows.to_dict(orient="records"),
        "meta": {
            "rows": len(rows),
            "days_requested": days,
            "avg_confidence": round(rows["confidence_score"].mean(), 3) if len(rows) else 0,
        }
    }

    redis_client.setex(cache_key, REDIS_TTL, json.dumps(payload, default=str))
    response = JSONResponse(content=payload)
    response.headers["X-Cache"] = "MISS"
    return response
