from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.snowflake.operators.snowflake import SnowflakeOperator
from airflow.models.baseoperator import chain
import os
from airflow.models import Variable

now = datetime.now()
database_name ='mwaa_db'
schema_name = 'mwaa_schema'
storage_int_name = 'mwaa_citibike_storage_int'
stage_name = 'mwaa_citibike_stg'
bucket_name=Variable.get("destination_bucket")
destination_bucket_path = 's3://' + bucket_name + '/'
aws_role_arn=Variable.get("aws_role_arn")

DEFAULT_ARGS = {
    'owner': 'airflow',
    'snowflake_conn_id': 'snowflake_conn_accountadmin',
    'depends_on_past': False,
    'email': ['airflow@example.com'],
    'email_on_failure': False,
    'email_on_retry': False,
    'start_date': datetime(now.year,now.month,now.day,now.hour),
    'retries': 3,
    'retry_delay': timedelta(minutes=1),
}

with DAG(
    dag_id=os.path.basename(__file__).replace(".py", ""),
    default_args=DEFAULT_ARGS,
    tags=['Snowflake','Citibike','DAG2'],
    schedule_interval=None
) as dag:

    # Create database
    create_database = SnowflakeOperator(
        task_id='create_database',
        sql='mwaa_snowflake_queries/create_database.sql',
        params={"database_name":database_name}
    )

    # Create a stage for storing content from S3 to sowflake
    create_schema = SnowflakeOperator(
        task_id='create_schema',
        sql='mwaa_snowflake_queries/create_schema.sql',
        database=database_name,
        params={"schema_name": schema_name}
    )

    # Create a file format based on the data
    create_storage_int = SnowflakeOperator(
        task_id='create_storage_int',
        database=database_name,
        schema=schema_name,
        sql='mwaa_snowflake_queries/create_storage_int.sql',
        params={"storage_int_name": storage_int_name, "aws_role_arn": aws_role_arn, "destination_bucket_path": destination_bucket_path}
    )

    # Create a table to move data from stage to table
    create_stage = SnowflakeOperator(
        task_id='create_stage',
        database=database_name,
        schema=schema_name,
        sql='mwaa_snowflake_queries/create_stage.sql',
        params={"stage_name": stage_name, "storage_int_name": storage_int_name, "destination_bucket_path": destination_bucket_path}
    )

    create_database >> create_schema >> create_storage_int >> create_stage
