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


@router.get("/")
@limiter.limit("10/minute")
def get_seller_performance(request: Request, limit: int = 20, sort_by: str = "revenue"):
    cache_key = f"seller_perf:v1:limit={limit}:sort={sort_by}"
    cached = redis_client.get(cache_key)
    if cached:
        r = JSONResponse(content=json.loads(cached))
        r.headers["X-Cache"] = "HIT"
        return r

    order_col = {
        "revenue": "total_revenue",
        "on_time": "on_time_rate",
        "orders": "total_orders",
    }.get(sort_by, "total_revenue")

    con = duckdb.connect(DUCKDB_PATH, read_only=True)
    rows = con.execute(f"""
        SELECT
            seller_id,
            total_orders,
            ROUND(total_revenue, 2)     AS total_revenue,
            ROUND(avg_order_value, 2)   AS avg_order_value,
            ROUND(avg_delivery_days, 1) AS avg_delivery_days,
            ROUND(on_time_rate, 4)      AS on_time_rate,
            cancelled_orders,
            revenue_quartile,
            on_time_rank,
            CAST(freshness_ts AS VARCHAR)   AS freshness_ts,
            confidence_score,
            data_source,
            CAST(last_order_at AS VARCHAR)  AS last_order_at
        FROM main_marts.mart_seller_performance
        ORDER BY {order_col} DESC NULLS LAST
        LIMIT {limit}
    """).fetchdf()
    con.close()

    payload = {
        "data": rows.to_dict(orient="records"),
        "meta": {"rows": len(rows), "sorted_by": sort_by},
    }
    redis_client.setex(cache_key, REDIS_TTL, json.dumps(payload, default=str))
    r = JSONResponse(content=payload)
    r.headers["X-Cache"] = "MISS"
    return r
