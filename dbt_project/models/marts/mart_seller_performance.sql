-- mart_seller_performance.sql
-- Agent-optimized mart: seller rankings with freshness + confidence metadata
-- Read by /seller-performance API endpoint and the Analyst agent

WITH items AS (
    SELECT * FROM {{ ref('stg_order_items') }}
),

orders AS (
    SELECT * FROM {{ ref('stg_orders') }}
),

seller_stats AS (
    SELECT
        i.seller_id,
        COUNT(DISTINCT i.order_id)                    AS total_orders,
        SUM(i.unit_price)                             AS total_revenue,
        AVG(i.unit_price)                             AS avg_order_value,
        AVG(o.actual_delivery_days) FILTER (
            WHERE o.actual_delivery_days IS NOT NULL
              AND o.actual_delivery_days > 0
        )                                             AS avg_delivery_days,
        AVG(CAST(o.delivered_on_time AS INTEGER)) FILTER (
            WHERE o.delivered_on_time IS NOT NULL
        )                                             AS on_time_rate,
        COUNT(*) FILTER (
            WHERE o.order_status = 'canceled'
        )                                             AS cancelled_orders,
        MAX(o.purchased_at)                           AS last_order_at
    FROM items i
    LEFT JOIN orders o USING (order_id)
    GROUP BY i.seller_id
),

ranked AS (
    SELECT
        *,
        NTILE(4) OVER (ORDER BY total_revenue DESC)  AS revenue_quartile,
        RANK() OVER (ORDER BY on_time_rate DESC NULLS LAST) AS on_time_rank,

        -- Agent metadata
        CURRENT_TIMESTAMP AS freshness_ts,
        CASE
            WHEN DATEDIFF('hour', last_order_at, CURRENT_TIMESTAMP) < 24 THEN 1.0
            WHEN DATEDIFF('hour', last_order_at, CURRENT_TIMESTAMP) < 72 THEN 0.8
            ELSE 0.5
        END AS confidence_score,
        'olist_orders_csv' AS data_source
    FROM seller_stats
)

SELECT * FROM ranked
ORDER BY total_revenue DESC
