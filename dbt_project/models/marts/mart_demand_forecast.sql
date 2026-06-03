-- mart_demand_forecast.sql
-- Agent-optimized mart: category demand trends from streaming events
-- Read by /demand-forecast endpoint

WITH events AS (
    SELECT * FROM raw.order_events
),

category_trends AS (
    SELECT
        product_category,
        DATE_TRUNC('hour', event_ts)           AS hour_bucket,
        COUNT(*)                               AS event_count,
        SUM(order_value)                       AS total_value,
        AVG(order_value)                       AS avg_order_value,
        COUNT(*) FILTER (
            WHERE event_type = 'order_placed'
        )                                      AS new_orders,
        COUNT(*) FILTER (
            WHERE event_type = 'order_cancelled'
        )                                      AS cancellations,
        MAX(event_ts)                          AS last_event_at
    FROM events
    WHERE event_ts >= CURRENT_TIMESTAMP - INTERVAL 24 HOUR
    GROUP BY 1, 2
),

with_metadata AS (
    SELECT
        *,
        -- 7-period moving average on event count for trend signal
        AVG(event_count) OVER (
            PARTITION BY product_category
            ORDER BY hour_bucket
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) AS event_count_7h_avg,

        CURRENT_TIMESTAMP AS freshness_ts,
        -- Streaming data: freshness decays faster (5-min windows)
        CASE
            WHEN DATEDIFF('minute', last_event_at, CURRENT_TIMESTAMP) < 10 THEN 1.0
            WHEN DATEDIFF('minute', last_event_at, CURRENT_TIMESTAMP) < 30 THEN 0.85
            WHEN DATEDIFF('minute', last_event_at, CURRENT_TIMESTAMP) < 60 THEN 0.6
            ELSE 0.3
        END AS confidence_score,
        'streaming_simulation' AS data_source
    FROM category_trends
)

SELECT * FROM with_metadata
ORDER BY product_category, hour_bucket DESC
