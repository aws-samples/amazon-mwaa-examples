-- models/customer_orders.sql
{{ config(
    materialized='external',
    location='s3://{{ var("s3_output_bucket") }}/{{ var("s3_output_prefix") }}/customer_orders.parquet',
    format='parquet'
) }}
select
    c.customer_id,
    c.customer_name,
    c.email,
    count(o.order_id) as total_orders,
    coalesce(sum(o.amount), 0) as total_amount,
    min(o.order_date) as first_order_date,
    max(o.order_date) as last_order_date
from read_parquet('s3://{{ var("s3_output_bucket") }}/{{ var("s3_output_prefix") }}/stg_customers.parquet') c
left join read_parquet('s3://{{ var("s3_output_bucket") }}/{{ var("s3_output_prefix") }}/stg_orders.parquet') o
    on c.customer_id = o.customer_id
group by c.customer_id, c.customer_name, c.email
