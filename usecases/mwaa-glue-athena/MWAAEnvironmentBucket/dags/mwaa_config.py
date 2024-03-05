from airflow.models import Variable

import os

BUCKET_NAME = Variable.get("artifact_bucket")
CRAWLER_CONFIG = {"Name": "curated_layer_crawler"}
ATHENA_KEY = 'athenasql/'
DATASET_NAME = "data-pipeline-mapped-dynamic-dataset"
REGION=os.getenv("AWS_DEFAULT_REGION")
RESULTS_LOCATION=f's3://{BUCKET_NAME}/athena/results/'
GLUE_CONCURRENCY=10
GLUE_POOL="glue_pool"
GLUE_CRAWLER_CONCURRENCY=1
GLUE_CRAWLER_POOL="glue_crawler_pool"
POSTGRES_CONNECTION="postgres_default"
