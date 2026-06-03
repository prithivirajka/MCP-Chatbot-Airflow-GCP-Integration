"""
FastAPI application entry point.
Includes: request logging middleware, Redis setup, rate limiting, router registration.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import redis
import duckdb
import time
import uuid
import os
from loguru import logger

from api.routers import supply_health, seller_performance, demand_forecast, agent_status

# ── App setup ──────────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Agent Data Platform API",
    description="Serving layer for supply chain AI agents. All endpoints include freshness and confidence metadata.",
    version="1.0.0",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── Redis ──────────────────────────────────────────────────────────────────────
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

# ── DuckDB ─────────────────────────────────────────────────────────────────────
DUCKDB_PATH = os.getenv("DUCKDB_PATH", "./data/duckdb/platform.duckdb")

# ── Request logging middleware ─────────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    Logs every request to DuckDB request_log table.
    Captures: agent_id, endpoint, latency, cache_hit.
    This powers the observability dashboard.
    """
    start = time.time()
    agent_id = request.headers.get("X-Agent-ID", "unknown")
    request_id = str(uuid.uuid4())

    response = await call_next(request)

    latency_ms = round((time.time() - start) * 1000, 2)
    cache_hit = response.headers.get("X-Cache", "MISS") == "HIT"

    try:
        con = duckdb.connect(DUCKDB_PATH)
        con.execute("CREATE SCHEMA IF NOT EXISTS main_observability")
        con.execute("""
            CREATE TABLE IF NOT EXISTS main_observability.request_log (
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
        con.execute("""
            INSERT INTO main_observability.request_log
            (request_id, agent_id, endpoint, method, status_code, latency_ms, cache_hit)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [
            request_id,
            agent_id,
            request.url.path,
            request.method,
            response.status_code,
            latency_ms,
            cache_hit,
        ])
        con.close()
    except Exception as e:
        logger.warning(f"Request log write failed: {e}")

    logger.info(
        f"{request.method} {request.url.path} | "
        f"agent={agent_id} status={response.status_code} "
        f"latency={latency_ms}ms cache={'HIT' if cache_hit else 'MISS'}"
    )
    return response


# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(supply_health.router,       prefix="/supply-health",       tags=["Supply Health"])
app.include_router(seller_performance.router,  prefix="/seller-performance",  tags=["Sellers"])
app.include_router(demand_forecast.router,     prefix="/demand-forecast",     tags=["Demand"])
app.include_router(agent_status.router,        prefix="/agent-status",        tags=["Metadata"])


@app.get("/health")
def health_check():
    return {"status": "ok"}
