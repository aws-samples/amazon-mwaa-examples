from airflow.decorators import dag, task
from airflow.operators.bash_operator import BashOperator
# from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook

from airflow.models.connection import Connection
from airflow import settings

from datetime import datetime
import os, mwaa_config

DAG_ID = os.path.basename(__file__).replace(".py", "")

@task()
def get_connection():
    conn=PostgresHook.get_connection(mwaa_config.POSTGRES_CONNECTION)
    bash_command=f"cd /usr/local/airflow/dags/sampledb; export PGPASSWORD={conn.password}; psql --host={conn.host} --port={conn.port} --dbname={conn.schema} --username={conn.login} -f /usr/local/airflow/dags/sampledb/install-postgresql.sql"

    return bash_command

@dag(
    dag_id = DAG_ID,
    start_date=datetime(2022, 1, 1),
    catchup=False,   
    schedule_interval = "@once",
    template_searchpath=["/usr/local/airflow/dags/sampledb"],
)
def create_resources_dag():
    connection_command=get_connection()

    create_tables = BashOperator(
        task_id="create_tables",
        bash_command=connection_command
    )

    create_glue_pool = BashOperator(
        task_id="create_glue_pool",
        bash_command=f"airflow pools set -o plain -v {mwaa_config.GLUE_POOL} {mwaa_config.GLUE_CONCURRENCY} \"This pool limits glue jobs to the maximum concurrency of the Glue service\""
    )

    create_glue_crawler_pool = BashOperator(
        task_id="create_glue_crawler_pool",
        bash_command=f"airflow pools set -o plain -v {mwaa_config.GLUE_CRAWLER_POOL} {mwaa_config.GLUE_CRAWLER_CONCURRENCY} \"This pool limits glue jobs to the maximum concurrency of the Glue service\""
    )

create_resources_instance = create_resources_dag()
