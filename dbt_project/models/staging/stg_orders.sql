-- stg_orders.sql
-- Cleans and types the raw Olist orders table

WITH source AS (
    SELECT * FROM raw.orders
),

cleaned AS (
    SELECT
        order_id,
        customer_id,
        order_status,
        CAST(order_purchase_timestamp AS TIMESTAMP)  AS purchased_at,
        CAST(order_approved_at AS TIMESTAMP)         AS approved_at,
        CAST(order_delivered_carrier_date AS TIMESTAMP) AS shipped_at,
        CAST(order_delivered_customer_date AS TIMESTAMP) AS delivered_at,
        CAST(order_estimated_delivery_date AS TIMESTAMP) AS estimated_delivery_at,

        -- Derived fields
        CASE
            WHEN order_delivered_customer_date IS NOT NULL
             AND order_estimated_delivery_date IS NOT NULL
            THEN CAST(order_delivered_customer_date AS TIMESTAMP)
               <= CAST(order_estimated_delivery_date AS TIMESTAMP)
            ELSE NULL
        END AS delivered_on_time,

        DATEDIFF(
            'day',
            CAST(order_purchase_timestamp AS TIMESTAMP),
            CAST(order_delivered_customer_date AS TIMESTAMP)
        ) AS actual_delivery_days,

        ingested_at
    FROM source
    WHERE order_id IS NOT NULL
)

SELECT * FROM cleaned
