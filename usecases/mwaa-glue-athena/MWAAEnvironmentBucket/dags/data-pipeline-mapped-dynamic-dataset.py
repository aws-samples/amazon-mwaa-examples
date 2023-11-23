from airflow.decorators import dag, task
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
from airflow.providers.amazon.aws.operators.glue_crawler import GlueCrawlerOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.datasets import Dataset
from datetime import datetime
import os, mwaa_config

DAG_ID = os.path.basename(__file__).replace(".py", "")

@task()
def get_tables_fn():
    pg_request = "SELECT * FROM pg_tables where schemaname = 'dms_sample'"
    pg_hook = PostgresHook(postgres_conn_id=mwaa_config.POSTGRES_CONNECTION,schema='sportstickets')
    connection = pg_hook.get_conn()
    cursor = connection.cursor()
    cursor.execute(pg_request)
    sources = cursor.fetchall()
    
    table_list = []
    for source in sources:
        print("Source: {0}".format(source))
        table_list.append({"--table_name":source[1],"--bucket_name":mwaa_config.BUCKET_NAME})

    return table_list

@dag(
    dag_id = DAG_ID,
    start_date=datetime(2022, 1, 1),
    catchup=False,   
    schedule_interval = None,
)
def ingestion_dag():
    get_tables=get_tables_fn()        
    ingest_rds = GlueJobOperator.partial(
        task_id="ingest_rds",
        job_name="ingest_rds_data",
        region_name=mwaa_config.REGION,
        pool=mwaa_config.GLUE_POOL
    ).expand(script_args=get_tables)

    c2p = GlueJobOperator.partial(
        task_id="convert-to-parquet",
        job_name="convert_to_parquet",
        region_name=mwaa_config.REGION,
        pool=mwaa_config.GLUE_POOL
    ).expand(script_args=get_tables)

    curated_layer = GlueCrawlerOperator(
        task_id="curated_layer",
        config=mwaa_config.CRAWLER_CONFIG,
        pool=mwaa_config.GLUE_CRAWLER_POOL,
        outlets=[Dataset(mwaa_config.DATASET_NAME)],        
    )

    ingest_rds >> c2p >> curated_layer

ingestion_dag_instance = ingestion_dag()