"""
CrewAI multi-agent supply chain analysis system.
3 agents in sequence: Retriever → Analyst → Reporter

Uses Anthropic Claude via langchain-anthropic.
Run with: python agents/run_agents.py
"""

import os
from crewai import Agent, Task, Crew, Process
from langchain_anthropic import ChatAnthropic
import httpx
from dotenv import load_dotenv

load_dotenv()

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
AGENT_ID_RETRIEVER = "agent-retriever-v1"
AGENT_ID_ANALYST   = "agent-analyst-v1"
AGENT_ID_REPORTER  = "agent-reporter-v1"

llm = ChatAnthropic(
    model=os.getenv("LLM_MODEL", "claude-sonnet-4-5"),
    anthropic_api_key=ANTHROPIC_API_KEY,
    temperature=0.2,
    max_tokens=2048,
)


# ── Tool functions ─────────────────────────────────────────────────────────────

def fetch_supply_health(days: int = 3000) -> dict:
    resp = httpx.get(f"{API_BASE}/supply-health/", params={"days": days},
                     headers={"X-Agent-ID": AGENT_ID_RETRIEVER}, timeout=30)
    resp.raise_for_status()
    return resp.json()

def fetch_seller_performance(limit: int = 10) -> dict:
    resp = httpx.get(f"{API_BASE}/seller-performance/", params={"limit": limit, "sort_by": "revenue"},
                     headers={"X-Agent-ID": AGENT_ID_RETRIEVER}, timeout=30)
    resp.raise_for_status()
    return resp.json()

def fetch_demand_forecast(hours: int = 6) -> dict:
    resp = httpx.get(f"{API_BASE}/demand-forecast/", params={"hours": hours},
                     headers={"X-Agent-ID": AGENT_ID_RETRIEVER}, timeout=30)
    resp.raise_for_status()
    return resp.json()

def check_data_freshness() -> dict:
    resp = httpx.get(f"{API_BASE}/agent-status/",
                     headers={"X-Agent-ID": AGENT_ID_RETRIEVER}, timeout=10)
    resp.raise_for_status()
    return resp.json()


def fetch_all_platform_data() -> str:
    results = {}
    try: results["freshness"] = check_data_freshness()
    except Exception as e: results["freshness"] = {"error": str(e)}
    try: results["supply_health"] = fetch_supply_health(days=3000)
    except Exception as e: results["supply_health"] = {"error": str(e)}
    try: results["seller_performance"] = fetch_seller_performance(limit=10)
    except Exception as e: results["seller_performance"] = {"error": str(e)}
    try: results["demand_forecast"] = fetch_demand_forecast(hours=6)
    except Exception as e: results["demand_forecast"] = {"error": str(e)}

    lines = ["=== PLATFORM DATA SNAPSHOT ===\n"]

    freshness = results.get("freshness", {})
    lines.append("--- Mart Freshness & Confidence ---")
    for mart, info in freshness.get("marts", {}).items():
        if "error" not in info:
            lines.append(f"  {mart}: confidence={info['avg_confidence']}, rows={info['row_count']}, healthy={info['healthy']}")
        else:
            lines.append(f"  {mart}: ERROR - {info['error']}")

    lines.append("\n--- Supply Health KPIs ---")
    sh = results.get("supply_health", {})
    data = sh.get("data", [])
    if data:
        total_orders = sum(r.get("total_orders", 0) for r in data)
        delivered = sum(r.get("delivered_orders", 0) for r in data)
        cancelled = sum(r.get("cancelled_orders", 0) for r in data)
        otd_rows = [r for r in data if r.get("on_time_delivery_rate")]
        avg_otd = sum(r["on_time_delivery_rate"] for r in otd_rows) / max(len(otd_rows), 1)
        day_rows = [r for r in data if r.get("avg_delivery_days")]
        avg_days = sum(r["avg_delivery_days"] for r in day_rows) / max(len(day_rows), 1)
        lines.append(f"  Total orders: {total_orders:,}")
        lines.append(f"  Delivered: {delivered:,} | Cancelled: {cancelled:,}")
        lines.append(f"  Avg on-time delivery rate: {avg_otd:.1%}")
        lines.append(f"  Avg delivery days: {avg_days:.1f}")
        lines.append(f"  Data points: {len(data)} daily buckets | Confidence: {sh.get('meta', {}).get('avg_confidence', 'N/A')}")
    else:
        lines.append("  No supply health data available")

    lines.append("\n--- Top 10 Sellers by Revenue ---")
    sp = results.get("seller_performance", {})
    for i, seller in enumerate(sp.get("data", [])[:10], 1):
        lines.append(
            f"  {i}. {seller['seller_id'][:12]}... | revenue=${seller['total_revenue']:,.0f} | "
            f"orders={seller['total_orders']} | on_time={seller.get('on_time_rate', 0):.1%} | "
            f"avg_delivery={seller.get('avg_delivery_days', 'N/A')} days"
        )

    lines.append("\n--- Demand Forecast (last 6 hours by category) ---")
    df_data = results.get("demand_forecast", {}).get("data", [])
    if df_data:
        cat_totals = {}
        for row in df_data:
            cat = row["product_category"]
            if cat not in cat_totals:
                cat_totals[cat] = {"events": 0, "value": 0, "new_orders": 0}
            cat_totals[cat]["events"] += row.get("event_count", 0)
            cat_totals[cat]["value"] += row.get("total_value", 0)
            cat_totals[cat]["new_orders"] += row.get("new_orders", 0)
        for cat, totals in sorted(cat_totals.items(), key=lambda x: x[1]["events"], reverse=True):
            lines.append(f"  {cat}: {totals['events']} events, ${totals['value']:,.0f} value, {totals['new_orders']} new orders")
    else:
        lines.append("  No demand forecast data in window")

    return "\n".join(lines)


# ── Agents ─────────────────────────────────────────────────────────────────────

retriever_agent = Agent(
    role="Supply Chain Data Retriever",
    goal="Retrieve and summarize fresh supply chain data from the platform API.",
    backstory=(
        "You are a precision data retrieval agent. You pull KPIs, seller rankings, "
        "and demand signals from a live supply chain data platform. You report exactly "
        "what the data shows — no hallucination, no guessing."
    ),
    llm=llm, verbose=True,
)

analyst_agent = Agent(
    role="Supply Chain Analyst",
    goal="Analyze supply chain data to identify the top 3 actionable insights.",
    backstory=(
        "You are a senior supply chain analyst with expertise in e-commerce logistics. "
        "You synthesize KPIs into clear, quantified findings. Always reference specific numbers."
    ),
    llm=llm, verbose=True,
)

reporter_agent = Agent(
    role="Supply Chain Report Writer",
    goal="Write a concise executive supply chain brief under 400 words.",
    backstory=(
        "You produce clear, actionable supply chain briefings for senior stakeholders. "
        "Your reports are data-driven and always include specific numbers."
    ),
    llm=llm, verbose=True,
)


# ── Fetch data ─────────────────────────────────────────────────────────────────
print("Fetching platform data...")
platform_data = fetch_all_platform_data()
print("Data fetched. Starting agent crew...\n")

# ── Tasks ──────────────────────────────────────────────────────────────────────

task_retrieve = Task(
    description=(
        f"Here is the current supply chain platform data:\n\n{platform_data}\n\n"
        "Summarize this data clearly: key metrics, data freshness/confidence, "
        "and any notable patterns. Be specific with numbers."
    ),
    agent=retriever_agent,
    expected_output="Structured summary of supply chain KPIs, top sellers, and demand trends with confidence scores.",
)

task_analyze = Task(
    description=(
        "Using the retriever's data summary, identify:\n"
        "1. Delivery performance assessment (on-time rate, avg delivery days)\n"
        "2. Top 3 sellers by revenue and their on-time delivery rates\n"
        "3. Which product categories show highest demand in the last 6 hours\n"
        "4. Any sellers with on_time_rate < 0.7 — flag as at-risk\n"
        "5. Any risks or anomalies worth flagging\n"
        "Reference specific numbers from the data."
    ),
    agent=analyst_agent,
    expected_output="Analytical summary with 3-5 quantified findings and identified risks.",
)

task_report = Task(
    description=(
        "Write the supply chain executive brief based on the analyst findings.\n"
        "Use this exact format:\n\n"
        "## Executive Summary\n(2-3 sentences)\n\n"
        "## Key Metrics\n(bullet list with numbers)\n\n"
        "## Top Risks\n(2-3 items)\n\n"
        "## Recommended Actions\n(2-3 items)\n\n"
        "## Data Quality Note\n(confidence score and freshness)\n\n"
        "Keep total length under 400 words."
    ),
    agent=reporter_agent,
    expected_output="Formatted executive brief under 400 words.",
)

# ── Crew ───────────────────────────────────────────────────────────────────────

crew = Crew(
    agents=[retriever_agent, analyst_agent, reporter_agent],
    tasks=[task_retrieve, task_analyze, task_report],
    process=Process.sequential,
    verbose=True,
)

if __name__ == "__main__":
    print("\n" + "="*60)
    print("Supply Chain Agent Platform — Running crew...")
    print("="*60 + "\n")
    result = crew.kickoff()
    print("\n" + "="*60)
    print("FINAL REPORT")
    print("="*60)
    print(result)
    with open("agents/last_report.md", "w") as f:
        f.write(str(result))
    print("\nReport saved to agents/last_report.md")
