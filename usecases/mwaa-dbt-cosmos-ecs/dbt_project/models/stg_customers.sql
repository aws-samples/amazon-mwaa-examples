-- models/stg_customers.sql
{{ config(
    materialized='external',
    location='s3://{{ var("s3_output_bucket") }}/{{ var("s3_output_prefix") }}/stg_customers.parquet',
    format='parquet'
) }}
select
    id as customer_id,
    customer_name,
    email,
    created_at
from read_parquet('s3://{{ var("s3_output_bucket") }}/{{ var("s3_output_prefix") }}/seeds/raw_customers.parquet')
