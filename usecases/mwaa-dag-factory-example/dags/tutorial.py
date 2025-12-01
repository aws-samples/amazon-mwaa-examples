from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor
from airflow.providers.amazon.aws.operators.glue_crawler import GlueCrawlerOperator


# [START default_args]
# These args will get passed on to each operator
# You can override them on a per-task basis during operator initialization
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email': ['airflow@example.com'],
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
    # 'queue': 'bash_queue',
    # 'pool': 'backfill',
    # 'priority_weight': 10,
    # 'end_date': datetime(2016, 1, 1),
    # 'wait_for_downstream': False,
    # 'dag': dag,
    # 'sla': timedelta(hours=2),
    # 'execution_timeout': timedelta(seconds=300),
    # 'on_failure_callback': some_function,
    # 'on_success_callback': some_other_function,
    # 'on_retry_callback': another_function,
    # 'sla_miss_callback': yet_another_function,
    # 'trigger_rule': 'all_success'
}
# [END default_args]

with DAG(
    'tutorial',
    default_args=default_args,
    description='A simple tutorial DAG',
    schedule="@daily",
    start_date=datetime(2021, 1, 1),
    catchup=False,
) as dag:

    s3_sensor = S3KeySensor(
        task_id='s3_sensor',
        bucket_name='mwaa-data-pipeline-workshop-mwaabucket-ncwa8kizckqv',
        bucket_key='data/raw/green*',
        wildcard_match=True
    )

    glue_crawler = GlueCrawlerOperator(
        task_id="glue_crawler",
        config={
            "Name": "airflow-workshop-raw-green-crawler",
            "Role": "arn:aws:iam::585906642819:role/mwaa-data-pipeline-workshop-GlueServiceRole-SwpgIH4goDqh",
            "DatabaseName": "default",
            "Targets": {"S3Targets": [{"Path": "mwaa-data-pipeline-workshop-mwaabucket-ncwa8kizckqv/data/raw/green"}]}
        }
    )

    s3_sensor >> glue_crawler