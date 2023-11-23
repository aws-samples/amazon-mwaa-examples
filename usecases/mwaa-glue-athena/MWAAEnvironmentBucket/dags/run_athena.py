from airflow.decorators import dag, task
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.providers.amazon.aws.operators.athena import AthenaOperator
from airflow.datasets import Dataset
from datetime import datetime
import os, mwaa_config

DAG_ID = os.path.basename(__file__).replace(".py", "")

def data_from_s3(bucket_name,table_name):
    s3 = S3Hook()
    data = s3.read_key(bucket_name = mwaa_config.BUCKET_NAME, key = mwaa_config.ATHENA_KEY+table_name)
    return data

@dag(
    dag_id = DAG_ID,
    start_date=datetime(2022, 1, 1),
    catchup=False,   
    schedule=None,
)
def sql_dag():
    create_table_sporting_event_info_agg = AthenaOperator(
        task_id="create_table_sporting_event_info_agg",
        query=data_from_s3(mwaa_config.BUCKET_NAME,'sporting_event_info_agg'),
        database='curated_db',
        output_location=f"s3://" + mwaa_config.BUCKET_NAME + "/athena/create_table_sporting_event_info_agg/",
    )

    create_table_sporting_event_ticket_info_agg = AthenaOperator(
        task_id="create_table_sporting_event_ticket_info_agg",
        query=data_from_s3(mwaa_config.BUCKET_NAME,'sporting_event_ticket_info_agg'),
        database='curated_db',
        output_location=f"s3://" + mwaa_config.BUCKET_NAME + "/athena/create_table_sporting_event_ticket_info_agg/",
    )

    [create_table_sporting_event_info_agg,create_table_sporting_event_ticket_info_agg]

sql_dag_instance = sql_dag()
