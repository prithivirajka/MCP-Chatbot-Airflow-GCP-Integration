# Agent-Harnessed Supply Chain Analytics

An end-to-end data platform where multiple specialized AI agents consume production-grade pipelines through a FastAPI serving layer — with full observability into every data handoff.

## Architecture

```
Data Sources (REST APIs, CSV, Streaming Simulation)
                    ↓
        Apache Airflow (3 DAGs)
        Daily | Hourly | Every 5 min
                    ↓
         DuckDB (raw → staging → marts)
                    ↓
      dbt Core (agent-optimized transforms)
      freshness_ts + confidence_score on every row
                    ↓
     FastAPI Serving Layer (4 endpoints)
     Redis caching · Rate limiting · Request logging
                    ↓
   CrewAI Multi-Agent System (Anthropic Claude)
   Retriever → Analyst → Reporter
                    ↓
  Streamlit Observability Dashboard
  Agent call log · Latency metrics · Data freshness
```

## Stack

| Layer | Tool |
|---|---|
| Orchestration | Apache Airflow |
| Storage | DuckDB |
| Transformation | dbt Core |
| Serving API | FastAPI + Redis |
| Agents | CrewAI + Anthropic Claude |
| Observability | Streamlit |
| Containers | Docker Compose |

## Quick Start

### Prerequisites
- Docker Desktop
- Python 3.11+
- Anthropic API key
- Olist Brazilian E-Commerce dataset ([Kaggle](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce))

### 1. Clone and configure

```bash
git clone https://github.com/prithivirajka/Agent-Harnessed-Supply-Chain-Analytics.git
cd Agent-Harnessed-Supply-Chain-Analytics
cp .env.example .env
# Add your ANTHROPIC_API_KEY to .env
```

### 2. Set up Python environment

```bash
python -m venv .venv-app
.venv-app\Scripts\activate      # Windows
pip install -r requirements-app.txt
```

### 3. Load data and run dbt

```bash
# Place Olist CSVs in data/raw/
python scripts/init_db.py
python scripts/load_raw_csvs.py
cd dbt_project && dbt run --profiles-dir .
```

### 4. Start the platform

```bash
docker compose up
```

Services:
- API: http://localhost:8000/docs
- Dashboard: http://localhost:8501

### 5. Run the agents

```bash
.venv-app\Scripts\activate
python agents/run_agents.py
```

### 6. Start the streaming simulator (optional)

```bash
python scripts/stream_simulator.py
```

## Project Structure

```
├── dags/
│   ├── dag_01_daily_api_ingestion.py     # Open-Meteo weather API, daily
│   ├── dag_02_hourly_csv_ingestion.py    # Olist CSVs → DuckDB, hourly
│   └── dag_03_streaming_simulation.py   # Fake order events, every 5 min
├── dbt_project/
│   └── models/
│       ├── staging/                      # stg_orders, stg_order_items, stg_sellers
│       └── marts/                        # mart_supply_health, mart_seller_performance,
│                                         # mart_demand_forecast
│                                         # (all with freshness_ts + confidence_score)
├── api/
│   ├── main.py                           # FastAPI app + request logging middleware
│   └── routers/
│       ├── supply_health.py              # /supply-health/
│       ├── seller_performance.py         # /seller-performance/
│       ├── demand_forecast.py            # /demand-forecast/
│       └── agent_status.py              # /agent-status/
├── agents/
│   └── run_agents.py                     # CrewAI 3-agent crew
├── dashboard/
│   └── app.py                            # Streamlit observability dashboard
├── scripts/
│   ├── init_db.py                        # One-time DuckDB setup
│   ├── load_raw_csvs.py                  # Manual CSV ingestion
│   └── stream_simulator.py              # Standalone streaming simulator
├── Dockerfile.api
├── Dockerfile.dashboard
├── docker-compose.yml
└── .env.example
```

## Key Design Decisions

**Agent-optimized marts**: Every dbt mart includes `freshness_ts` and `confidence_score` columns. Agents check data quality before analysis — a 0.3 confidence score triggers a warning in the report, while 1.0 means fresh data. This mirrors how production ML pipelines handle data contracts.

**Request logging middleware**: Every API call is logged to `main_observability.request_log` in DuckDB — capturing agent ID, endpoint, latency, and cache hit. This is what powers the observability dashboard without any external monitoring infra.

**Separate Python environments**: Airflow requires SQLAlchemy < 2.0 while the rest of the stack needs >= 2.0. Two venvs (`requirements-airflow.txt` and `requirements-app.txt`) keep them isolated — the same pattern used in production data platforms.

## Resume Bullets

- Engineered 3 Airflow DAGs on different schedules landing supply chain data into DuckDB, with dbt transformation layer producing agent-optimized marts featuring freshness timestamps and confidence scoring across 634+ daily KPI records and 3,095 seller performance rows
- Built a FastAPI serving layer with 4 endpoints, Redis caching (10-min TTL), rate limiting, and request logging middleware capturing 100% of agent calls into DuckDB — enabling full data lineage from pipeline to consumer
- Orchestrated a CrewAI multi-agent system (Retriever → Analyst → Reporter) powered by Anthropic Claude that autonomously retrieves supply chain KPIs, identifies delivery anomalies across $1.99M seller revenue, and generates executive briefs — with observability surfaced in a real-time Streamlit dashboard; containerized in Docker Compose
