-- mart_supply_health.sql
-- Agent-optimized mart: delivery KPIs with freshness + confidence metadata
-- Removed date filter — Olist dataset is historical (2016-2018)

WITH orders AS (
    SELECT * FROM {{ ref('stg_orders') }}
),

daily_kpis AS (
    SELECT
        DATE_TRUNC('day', purchased_at)              AS kpi_date,
        COUNT(*)                                      AS total_orders,
        COUNT(*) FILTER (WHERE order_status = 'delivered') AS delivered_orders,
        COUNT(*) FILTER (WHERE order_status = 'canceled')  AS cancelled_orders,
        AVG(actual_delivery_days) FILTER (
            WHERE actual_delivery_days IS NOT NULL
              AND actual_delivery_days > 0
        )                                             AS avg_delivery_days,
        AVG(CAST(delivered_on_time AS INTEGER)) FILTER (
            WHERE delivered_on_time IS NOT NULL
        )                                             AS on_time_delivery_rate,
        CURRENT_TIMESTAMP                             AS refreshed_at
    FROM orders
    GROUP BY 1
),

with_metadata AS (
    SELECT
        *,
        CURRENT_TIMESTAMP AS freshness_ts,
        CASE
            WHEN DATEDIFF('hour', refreshed_at, CURRENT_TIMESTAMP) < 1  THEN 1.0
            WHEN DATEDIFF('hour', refreshed_at, CURRENT_TIMESTAMP) < 12 THEN 0.8
            WHEN DATEDIFF('hour', refreshed_at, CURRENT_TIMESTAMP) < 24 THEN 0.6
            ELSE 0.3
        END AS confidence_score,
        'olist_orders_csv' AS data_source
    FROM daily_kpis
)

SELECT * FROM with_metadata
ORDER BY kpi_date DESC
