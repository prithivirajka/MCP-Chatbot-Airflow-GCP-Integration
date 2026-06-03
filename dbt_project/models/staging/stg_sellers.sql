-- stg_sellers.sql

WITH source AS (
    SELECT * FROM raw.sellers
)

SELECT
    seller_id,
    seller_zip_code_prefix,
    seller_city,
    seller_state,
    ingested_at
FROM source
WHERE seller_id IS NOT NULL
