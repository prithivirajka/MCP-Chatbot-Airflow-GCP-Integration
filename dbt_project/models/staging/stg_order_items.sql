-- stg_order_items.sql

WITH source AS (
    SELECT * FROM raw.order_items
)

SELECT
    order_id,
    order_item_id,
    product_id,
    seller_id,
    CAST(shipping_limit_date AS TIMESTAMP) AS shipping_limit_at,
    CAST(price AS DOUBLE)                  AS unit_price,
    CAST(freight_value AS DOUBLE)          AS freight_value,
    unit_price + freight_value             AS total_item_value,
    ingested_at
FROM source
WHERE order_id IS NOT NULL
  AND product_id IS NOT NULL
