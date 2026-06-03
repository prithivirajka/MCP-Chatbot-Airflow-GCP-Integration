"""
Streamlit Observability Dashboard
Shows: agent call log, data served, latency metrics, cache hit rate
Run: streamlit run dashboard/app.py
"""

import streamlit as st
import duckdb
import pandas as pd
import plotly.express as px
import os

DUCKDB_PATH = os.getenv("DUCKDB_PATH", "./data/duckdb/platform.duckdb")

st.set_page_config(
    page_title="Agent Data Platform — Observability",
    page_icon="📊",
    layout="wide",
)

st.title("Agent Data Platform")
st.caption("Real-time observability into agent data requests and pipeline health")


@st.cache_data(ttl=30)
def load_request_log(hours: int = 24) -> pd.DataFrame:
    try:
        con = duckdb.connect(DUCKDB_PATH, read_only=True)
        df = con.execute(f"""
            SELECT *
            FROM main_observability.request_log
            WHERE logged_at >= CURRENT_TIMESTAMP - INTERVAL {hours} HOUR
            ORDER BY logged_at DESC
        """).fetchdf()
        con.close()
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=30)
def load_mart_freshness() -> pd.DataFrame:
    try:
        con = duckdb.connect(DUCKDB_PATH, read_only=True)
        rows = []
        for table in [
            "main_marts.mart_supply_health",
            "main_marts.mart_seller_performance",
            "main_marts.mart_demand_forecast",
        ]:
            try:
                r = con.execute(f"""
                    SELECT
                        '{table.split('.')[-1]}' AS mart,
                        MAX(freshness_ts)        AS last_refreshed,
                        AVG(confidence_score)    AS avg_confidence,
                        COUNT(*)                 AS row_count
                    FROM {table}
                """).fetchone()
                rows.append(r)
            except Exception:
                pass
        con.close()
        return pd.DataFrame(rows, columns=["mart", "last_refreshed", "avg_confidence", "row_count"])
    except Exception:
        return pd.DataFrame()


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    hours_window = st.selectbox("Time window", [1, 6, 12, 24, 48], index=3)
    st.button("Refresh data", on_click=st.cache_data.clear)

# ── Top metrics row ────────────────────────────────────────────────────────────
log_df = load_request_log(hours_window)
freshness_df = load_mart_freshness()

col1, col2, col3, col4 = st.columns(4)

if not log_df.empty:
    col1.metric("Total API calls", f"{len(log_df):,}")
    col2.metric("Unique agents", log_df["agent_id"].nunique())
    cache_hit_rate = log_df["cache_hit"].mean() * 100
    col3.metric("Cache hit rate", f"{cache_hit_rate:.1f}%")
    p95 = log_df["latency_ms"].quantile(0.95)
    col4.metric("p95 latency", f"{p95:.0f}ms")
else:
    col1.metric("Total API calls", "—")
    col2.metric("Unique agents", "—")
    col3.metric("Cache hit rate", "—")
    col4.metric("p95 latency", "—")
    st.info("No request data yet. Run `python agents/run_agents.py` to generate traffic.")

st.divider()

# ── Agent call log ─────────────────────────────────────────────────────────────
st.subheader("Agent call log")

if not log_df.empty:
    col_a, col_b = st.columns([2, 1])

    with col_a:
        calls_by_endpoint = log_df.groupby("endpoint").size().reset_index(name="calls")
        fig = px.bar(
            calls_by_endpoint, x="endpoint", y="calls",
            title="Calls per endpoint",
            color="calls", color_continuous_scale="Blues",
        )
        fig.update_layout(height=300, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        calls_by_agent = log_df.groupby("agent_id").size().reset_index(name="calls")
        fig2 = px.pie(
            calls_by_agent, names="agent_id", values="calls",
            title="Calls by agent",
        )
        fig2.update_layout(height=300)
        st.plotly_chart(fig2, use_container_width=True)

    log_df["logged_at"] = pd.to_datetime(log_df["logged_at"])
    fig3 = px.scatter(
        log_df, x="logged_at", y="latency_ms",
        color="cache_hit", symbol="endpoint",
        title="Latency over time (orange = cache MISS, blue = HIT)",
        labels={"latency_ms": "Latency (ms)", "logged_at": "Time"},
    )
    fig3.update_layout(height=300)
    st.plotly_chart(fig3, use_container_width=True)

    with st.expander("Raw request log"):
        st.dataframe(log_df[["logged_at", "agent_id", "endpoint", "status_code", "latency_ms", "cache_hit"]])

st.divider()

# ── Data freshness panel ───────────────────────────────────────────────────────
st.subheader("Mart freshness & confidence")

if not freshness_df.empty:
    for _, row in freshness_df.iterrows():
        conf = row["avg_confidence"] or 0
        color = "🟢" if conf >= 0.8 else "🟡" if conf >= 0.6 else "🔴"
        st.markdown(
            f"{color} **{row['mart']}** — "
            f"confidence: `{conf:.2f}` | "
            f"rows: `{int(row['row_count']):,}` | "
            f"last refreshed: `{row['last_refreshed']}`"
        )
else:
    st.warning("Mart tables not yet created. Run `dbt run` first.")

st.divider()
st.caption(f"Auto-refreshes every 30s · DuckDB path: {DUCKDB_PATH}")
