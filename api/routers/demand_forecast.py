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
REDIS_TTL = int(os.getenv("REDIS_TTL_SECONDS", 300))
redis_client = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)


@router.get("/")
@limiter.limit("10/minute")
def get_demand_forecast(request: Request, category: str = None, hours: int = 6):
    cache_key = f"demand:v1:cat={category}:h={hours}"
    cached = redis_client.get(cache_key)
    if cached:
        r = JSONResponse(content=json.loads(cached))
        r.headers["X-Cache"] = "HIT"
        return r

    cat_filter = f"AND product_category = '{category}'" if category else ""
    con = duckdb.connect(DUCKDB_PATH, read_only=True)
    rows = con.execute(f"""
        SELECT
            product_category,
            hour_bucket,
            event_count,
            ROUND(total_value, 2)           AS total_value,
            ROUND(avg_order_value, 2)       AS avg_order_value,
            new_orders,
            cancellations,
            ROUND(event_count_7h_avg, 1)    AS event_count_7h_avg,
            freshness_ts,
            confidence_score,
            data_source
        FROM main_marts.mart_demand_forecast
        WHERE hour_bucket >= CURRENT_TIMESTAMP - INTERVAL {hours} HOUR
        {cat_filter}
        ORDER BY product_category, hour_bucket DESC
    """).fetchdf()
    con.close()

    payload = {
        "data": rows.to_dict(orient="records"),
        "meta": {
            "rows": len(rows),
            "hours_window": hours,
            "category_filter": category,
        },
    }
    redis_client.setex(cache_key, REDIS_TTL, json.dumps(payload, default=str))
    r = JSONResponse(content=payload)
    r.headers["X-Cache"] = "MISS"
    return r
