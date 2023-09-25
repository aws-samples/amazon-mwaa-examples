create stage IF NOT EXISTS {{params.stage_name}}
  STORAGE_INTEGRATION = {{params.storage_int_name}}
  URL = '{{params.destination_bucket_path}}'