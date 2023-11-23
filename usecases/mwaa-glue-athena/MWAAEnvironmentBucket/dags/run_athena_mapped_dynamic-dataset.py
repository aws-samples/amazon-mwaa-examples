
from airflow.decorators import dag, task
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.providers.amazon.aws.operators.athena import AthenaOperator
from airflow.datasets import Dataset
from datetime import datetime
import os, mwaa_config

DAG_ID = os.path.basename(__file__).replace(".py", "")

@task()
def get_queries_fn():
    s3 = S3Hook()
    data = s3.list_keys(bucket_name=mwaa_config.BUCKET_NAME, prefix=mwaa_config.ATHENA_KEY, start_after_key=mwaa_config.ATHENA_KEY)
    return data

@task()
def data_from_s3(key_name):
    s3 = S3Hook()
    data = s3.read_key(bucket_name=mwaa_config.BUCKET_NAME, key=key_name)
    return data

@dag(
    dag_id = DAG_ID,
    start_date=datetime(2022, 1, 1),
    catchup=False,   
    schedule=[Dataset(mwaa_config.DATASET_NAME)],
)
def sql_dag():
    get_queries=get_queries_fn() 
    get_data_from_s3=data_from_s3.expand(key_name=get_queries)
    create_table_agg = AthenaOperator.partial(
        task_id="run_sql_athena",
        database='curated_db',
        output_location=mwaa_config.RESULTS_LOCATION
    ).expand(query=get_data_from_s3)
    
sql_dag_instance = sql_dag()
