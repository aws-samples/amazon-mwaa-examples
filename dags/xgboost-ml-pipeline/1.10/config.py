
# COMMON
REGION_NAME="us-east-1"

# AIRFLOW
AIRFLOW_DAG_ID="mwaa-sm-customer-churn-dag"

# GLUE
GLUE_ROLE_NAME="AmazonMWAA-Glue-Role"
GLUE_JOB_NAME_PREFIX="mwaa-xgboost-preprocess"
GLUE_JOB_SCRIPT_S3_BUCKET="glue-scripts-XXXXXXXXXXXX-us-east-1"
GLUE_JOB_SCRIPT_S3_KEY="mwaa-xgboost/preprocess-data/glue_etl.py"
DATA_S3_SOURCE="s3://datalake-XXXXXXXXXXXX-us-east-1/customer-churn/customer-churn.csv"
DATA_S3_DEST="s3://mlops-XXXXXXXXXXXX-us-east-1/mwaa-xgboost/processed/"

# SAGEMAKER
SAGEMAKER_ROLE_NAME="AmazonMWAA-SageMaker-Role"
SAGEMAKER_TRAINING_JOB_NAME_PREFIX="mwaa-sm-training-job"
SAGEMAKER_TRAINING_DATA_S3_SOURCE="s3://mlops-XXXXXXXXXXXX-us-east-1/mwaa-xgboost/processed/train/"
SAGEMAKER_VALIDATION_DATA_S3_SOURCE="s3://mlops-XXXXXXXXXXXX-us-east-1/mwaa-xgboost/processed/validation/"
SAGEMAKER_CONTENT_TYPE="text/csv"
SAGEMAKER_MODEL_NAME_PREFIX="mwaa-sm-customer-churn-model"
SAGEMAKER_ENDPOINT_NAME_PREFIX="mwaa-sm-endpoint" # endpoint names have a 63 max char limit
SAGEMAKER_MODEL_S3_DEST="s3://mlops-XXXXXXXXXXXX-us-east-1/mwaa-xgboost/model/"
