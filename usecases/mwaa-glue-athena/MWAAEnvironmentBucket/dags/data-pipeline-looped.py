from airflow.decorators import dag, task
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
from airflow.providers.amazon.aws.operators.glue_crawler import GlueCrawlerOperator
from datetime import datetime
import os, mwaa_config

DAG_ID = os.path.basename(__file__).replace(".py", "")

table_list=[
    {
        "--table_name":"sporting_event",
        "--bucket_name":mwaa_config.BUCKET_NAME
    },
    {
        "--table_name":"sport_team",
        "--bucket_name":mwaa_config.BUCKET_NAME
    }, 
    {
        "--table_name":"sport_location",
        "--bucket_name":mwaa_config.BUCKET_NAME
    }, 
    {
        "--table_name":"sporting_event_info",
        "--bucket_name":mwaa_config.BUCKET_NAME
    },
    {
        "--table_name":"sporting_event_ticket",
        "--bucket_name":mwaa_config.BUCKET_NAME
    },
    {
        "--table_name":"person",
        "--bucket_name":mwaa_config.BUCKET_NAME
    },
]

@dag(
    dag_id = DAG_ID,
    start_date=datetime(2022, 1, 1),
    catchup=False,   
    schedule_interval = None,
)
def ingestion_dag():
    curated_layer = GlueCrawlerOperator(
        task_id="curated_layer_crawler",
        pool=mwaa_config.GLUE_CRAWLER_POOL,
        config=mwaa_config.CRAWLER_CONFIG,
    )
    for t in table_list: 
        ingest_rds = GlueJobOperator(
            task_id=f"ingest_rds_{t['--table_name']}",
            job_name="ingest_rds_data",
            region_name=mwaa_config.REGION,
            pool=mwaa_config.GLUE_POOL,
            script_args=t)
        
        c2p = GlueJobOperator(
            task_id=f"convert-to-parquet_{t['--table_name']}",
            job_name="convert_to_parquet",
            region_name=mwaa_config.REGION,
            pool=mwaa_config.GLUE_POOL,
            script_args=t)  
        
        ingest_rds >> c2p >> curated_layer

ingestion_dag_instance = ingestion_dag()