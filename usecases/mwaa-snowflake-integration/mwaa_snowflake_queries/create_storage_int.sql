CREATE STORAGE INTEGRATION IF NOT EXISTS {{params.storage_int_name}}
  TYPE = EXTERNAL_STAGE
  STORAGE_PROVIDER = 'S3'
  ENABLED = TRUE
  STORAGE_AWS_ROLE_ARN = '{{params.aws_role_arn}}'
  STORAGE_ALLOWED_LOCATIONS = ('{{params.destination_bucket_path}}');