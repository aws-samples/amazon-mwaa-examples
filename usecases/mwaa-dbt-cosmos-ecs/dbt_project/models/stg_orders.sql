-- models/stg_orders.sql
{{ config(
    materialized='external',
    location='s3://{{ var("s3_output_bucket") }}/{{ var("s3_output_prefix") }}/stg_orders.parquet',
    format='parquet'
) }}
select
    id as order_id,
    customer_id,
    order_date,
    amount,
    status
from read_parquet('s3://{{ var("s3_output_bucket") }}/{{ var("s3_output_prefix") }}/seeds/raw_orders.parquet')
