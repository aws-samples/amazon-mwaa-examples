-- macros/export_to_s3.sql
{% macro export_seeds_to_s3() %}
  {% set bucket = var("s3_output_bucket") %}
  {% set prefix = var("s3_output_prefix") %}
  {% set seeds = ["raw_customers", "raw_orders"] %}
  {% for seed in seeds %}
    {% set s3_path = "s3://" ~ bucket ~ "/" ~ prefix ~ "/seeds/" ~ seed ~ ".parquet" %}
    {% set query %}
      COPY (SELECT * FROM {{ seed }}) TO '{{ s3_path }}' (FORMAT PARQUET)
    {% endset %}
    {% do run_query(query) %}
    {% do log("Exported " ~ seed ~ " to " ~ s3_path, info=True) %}
  {% endfor %}
{% endmacro %}
