from airflow.decorators import dag, task
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
from airflow.providers.amazon.aws.operators.glue_crawler import GlueCrawlerOperator
from datetime import datetime
import os, mwaa_config

DAG_ID = os.path.basename(__file__).replace(".py", "")

@dag(
    dag_id = DAG_ID,
    start_date=datetime(2022, 1, 1),
    catchup=False,   
    schedule_interval = None
)
def ingestion_dag():  
    ## Log ingest. Assumes Glue Job is already created
    ingest_rds_data_sporting_event = GlueJobOperator(
        task_id="ingest_rds_data_sporting_event",
        job_name="ingest_rds_data",
        script_args={
            "--table_name":"sporting_event",
            "--bucket_name":mwaa_config.BUCKET_NAME
        },
        region_name=mwaa_config.REGION,
        pool=mwaa_config.GLUE_POOL,
        verbose=True
    )

    ingest_rds_data_sport_team = GlueJobOperator(
        task_id="ingest_rds_data_sport_team",
        job_name="ingest_rds_data",
        script_args={
            "--table_name":"sport_team",
            "--bucket_name":mwaa_config.BUCKET_NAME
        },
        region_name=mwaa_config.REGION,
        pool=mwaa_config.GLUE_POOL,
        verbose=True
    )

    ingest_rds_data_sport_location = GlueJobOperator(
        task_id="ingest_rds_data_sport_location",
        job_name="ingest_rds_data",
        script_args={
            "--table_name":"sport_location",
            "--bucket_name":mwaa_config.BUCKET_NAME
        },
        region_name=mwaa_config.REGION,
        pool=mwaa_config.GLUE_POOL,
        verbose=True
    )

    ingest_rds_data_sporting_event_info = GlueJobOperator(
        task_id="ingest_rds_data_sporting_event_info",
        job_name="ingest_rds_data",
        script_args={
            "--table_name":"sporting_event_info",
            "--bucket_name":mwaa_config.BUCKET_NAME
        },
        region_name=mwaa_config.REGION,
        pool=mwaa_config.GLUE_POOL,
        verbose=True
    )

    ingest_rds_data_sporting_event_ticket = GlueJobOperator(
        task_id="ingest_rds_data_sporting_event_ticket",
        job_name="ingest_rds_data",
        script_args={
            "--table_name":"sporting_event_ticket",
            "--bucket_name":mwaa_config.BUCKET_NAME
        },
        region_name=mwaa_config.REGION,
        pool=mwaa_config.GLUE_POOL,
        verbose=True
    )

    ingest_rds_data_person = GlueJobOperator(
        task_id="ingest_rds_data_person",
        job_name="ingest_rds_data",
        script_args={
            "--table_name":"person",
            "--bucket_name":mwaa_config.BUCKET_NAME
        },
        region_name=mwaa_config.REGION,
        pool=mwaa_config.GLUE_POOL,
        verbose=True
    )

    c2p_sporting_event = GlueJobOperator(
        task_id="c2p_sporting_event",
        job_name="convert_to_parquet",
        script_args={
            "--table_name":"sporting_event",
            "--bucket_name":mwaa_config.BUCKET_NAME
        },
        region_name=mwaa_config.REGION,
        verbose=True
    )

    c2p_sport_team = GlueJobOperator(
        task_id="c2p_sport_team",
        job_name="convert_to_parquet",
        script_args={
            "--table_name":"sport_team",
            "--bucket_name":mwaa_config.BUCKET_NAME
        },
        region_name=mwaa_config.REGION,
        pool=mwaa_config.GLUE_POOL,
        verbose=True
    )

    c2p_sport_location = GlueJobOperator(
        task_id="c2p_sport_location",
        job_name="convert_to_parquet",
        script_args={
            "--table_name":"sport_location",
            "--bucket_name":mwaa_config.BUCKET_NAME
        },
        region_name=mwaa_config.REGION,
        pool=mwaa_config.GLUE_POOL,
        verbose=True
    )

    c2p_sporting_event_info = GlueJobOperator(
        task_id="c2p_sporting_event_info",
        job_name="convert_to_parquet",
        script_args={
            "--table_name":"sporting_event_info",
            "--bucket_name":mwaa_config.BUCKET_NAME
        },
        region_name=mwaa_config.REGION,
        pool=mwaa_config.GLUE_POOL,
        verbose=True
    )

    c2p_sporting_event_ticket = GlueJobOperator(
        task_id="c2p_sporting_event_ticket",
        job_name="convert_to_parquet",
        script_args={
            "--table_name":"sporting_event_ticket",
            "--bucket_name":mwaa_config.BUCKET_NAME
        },
        region_name=mwaa_config.REGION,
        pool=mwaa_config.GLUE_POOL,
        verbose=True
    )

    c2p_person = GlueJobOperator(
        task_id="c2p_person",
        job_name="convert_to_parquet",
        script_args={
            "--table_name":"person",
            "--bucket_name":mwaa_config.BUCKET_NAME
        },
        region_name=mwaa_config.REGION,
        pool=mwaa_config.GLUE_POOL,
        verbose=True
    )

    config = {"Name": "curated_layer_crawler"}

    curated_layer_crawler = GlueCrawlerOperator(
        task_id="curated_layer_crawler",
        config=mwaa_config.CRAWLER_CONFIG,
        pool=mwaa_config.GLUE_CRAWLER_POOL,
    )

    ingest_rds_data_sporting_event>>c2p_sporting_event>>curated_layer_crawler
    ingest_rds_data_sport_team>>c2p_sport_team>>curated_layer_crawler
    ingest_rds_data_sport_location>>c2p_sport_location>>curated_layer_crawler
    ingest_rds_data_sporting_event_info>>c2p_sporting_event_info>>curated_layer_crawler
    ingest_rds_data_sporting_event_ticket>>c2p_sporting_event_ticket>>curated_layer_crawler
    ingest_rds_data_person>>c2p_person>>curated_layer_crawler

ingestion_dag_instance = ingestion_dag()