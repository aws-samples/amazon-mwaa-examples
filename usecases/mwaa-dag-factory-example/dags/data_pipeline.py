from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor
from airflow.providers.amazon.aws.operators.glue_crawler import GlueCrawlerOperator
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
from airflow.providers.amazon.aws.operators.emr import (
    EmrServerlessCreateApplicationOperator,
    EmrServerlessStartJobOperator,
    EmrServerlessDeleteApplicationOperator,
)
from airflow.providers.amazon.aws.sensors.emr import EmrServerlessJobSensor
from airflow.providers.amazon.aws.operators.redshift_data import RedshiftDataOperator

with DAG(
    dag_id='example_data_pipeline',
    start_date=datetime(2025, 11, 1),
    schedule=None,  # Manual trigger (Airflow 3: schedule replaces schedule_interval)
    catchup=False,
    dagrun_timeout=timedelta(hours=2),
    default_args={
        'owner': 'airflow',
        'retries': 0,
        'retry_delay': timedelta(minutes=2)
    }
) as dag:

    s3_sensor = S3KeySensor(
        task_id='s3_sensor',
        bucket_name='{{S3_BUCKET_NAME}}',
        bucket_key='data/raw/green*',
        wildcard_match=True
    )

    glue_crawler = GlueCrawlerOperator(
        task_id="glue_crawler",
        config={
            "Name": "airflow-workshop-raw-green-crawler",
            "Role": "{{GLUE_ROLE_ARN}}",
            "DatabaseName": "default",
            "Targets": {"S3Targets": [{"Path": "{{S3_BUCKET_NAME}}/data/raw/green"}]}
        },
        retries=3,
        retry_delay=timedelta(minutes=2)
    )

    glue_job = GlueJobOperator(
        task_id="glue_job",
        job_name="nyc_raw_to_transform",
        script_location="s3://{{S3_BUCKET_NAME}}/scripts/glue/nyc_raw_to_transform.py",
        iam_role_name="{{GLUE_ROLE_NAME}}",
        create_job_kwargs={
            "GlueVersion": "4.0",
            "NumberOfWorkers": 2,
            "WorkerType": "G.1X",
            "Command": {
                "Name": "glueetl",
                "ScriptLocation": "s3://{{S3_BUCKET_NAME}}/scripts/glue/nyc_raw_to_transform.py",
                "PythonVersion": "3"
            }
        },
        script_args={
            '--dag_name': 'immersion_day_data_pipeline',
            '--task_id': 'glue_job',
            '--correlation_id': 'start_emr_serverless_job'
        }
    )

    create_emr_serverless_app = EmrServerlessCreateApplicationOperator(
        task_id="create_emr_serverless_app",
        aws_conn_id="aws_default",
        release_label="emr-6.9.0",
        job_type="SPARK",
        config={"name": "my-emr-serverless-app"}
    )

    emr_serverless_job = EmrServerlessStartJobOperator(
        task_id="start_emr_serverless_job",
        aws_conn_id="aws_default",
        application_id="{{ task_instance.xcom_pull('create_emr_serverless_app', key='return_value') }}",
        execution_role_arn="{{EMR_ROLE_ARN}}",
        job_driver={
            "sparkSubmit": {
                "entryPoint": "s3://{{S3_BUCKET_NAME}}/scripts/emr/nyc_aggregations.py",
                "entryPointArguments": [
                    "s3://{{S3_BUCKET_NAME}}/data/transformed/green",
                    "s3://{{S3_BUCKET_NAME}}/data/aggregated/green",
                    "immersion_day_data_pipeline",
                    "start_emr_serverless_job",
                    "start_emr_serverless_job"
                ],
                "sparkSubmitParameters": "--conf spark.executor.instances=2 --conf spark.executor.memory=4G --conf spark.executor.cores=2 --conf spark.executor.memoryOverhead=1G"
            }
        },
        configuration_overrides={
            "monitoringConfiguration": {
                "s3MonitoringConfiguration": {
                    "logUri": "s3://{{S3_BUCKET_NAME}}/logs/emr/data-pipeline/create_emr_cluster/"
                }
            }
        }
    )

    emr_serverless_job_sensor = EmrServerlessJobSensor(
        task_id="wait_for_emr_serverless_job",
        aws_conn_id="aws_default",
        application_id="{{ task_instance.xcom_pull('create_emr_serverless_app', key='return_value') }}",
        job_run_id="{{ task_instance.xcom_pull('start_emr_serverless_job', key='return_value') }}"
    )

    delete_app = EmrServerlessDeleteApplicationOperator(
        task_id="delete_app",
        application_id="{{ task_instance.xcom_pull('create_emr_serverless_app', key='return_value') }}"
    )

    drop_redshift_table = RedshiftDataOperator(
        task_id='drop_redshift_table',
        database='dev',
        sql="DROP TABLE IF EXISTS public.green;",
        workgroup_name='{{REDSHIFT_WORKGROUP}}',
        region_name='{{AWS_REGION}}',
        wait_for_completion=True
    )

    create_redshift_table = RedshiftDataOperator(
        task_id='create_redshift_table',
        database='dev',
        sql="""
        CREATE TABLE public.green (
            pulocationid BIGINT,
            trip_type BIGINT,
            payment_type BIGINT,
            total_fare_amount DOUBLE PRECISION
        )
        DISTSTYLE AUTO
        SORTKEY (pulocationid);
    """,
        workgroup_name='{{REDSHIFT_WORKGROUP}}',
        region_name='{{AWS_REGION}}',
        wait_for_completion=True
    )

    copy_to_redshift = RedshiftDataOperator(
        task_id='copy_to_redshift',
        database='dev',
        sql="""
        COPY public.green
        FROM 's3://{{S3_BUCKET_NAME}}/data/aggregated/green/'
        IAM_ROLE '{{REDSHIFT_ROLE_ARN}}'
        FORMAT AS PARQUET;
    """,
        workgroup_name='{{REDSHIFT_WORKGROUP}}',
        region_name='{{AWS_REGION}}',
        wait_for_completion=True
    )

    s3_sensor >> glue_crawler >> glue_job >> create_emr_serverless_app >> emr_serverless_job >> emr_serverless_job_sensor >> delete_app >> drop_redshift_table >> create_redshift_table >> copy_to_redshift