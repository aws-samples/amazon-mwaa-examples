from airflow import DAG, settings
from airflow.operators.python_operator import PythonOperator
from airflow.utils.dates import days_ago
from datetime import timedelta
from airflow.models.connection import Connection
from airflow.providers.amazon.aws.hooks.base_aws import AwsBaseHook
from airflow.providers.snowflake.operators.snowflake import SnowflakeOperator
import time
from airflow.operators.python import PythonOperator
import os,json,logging
from airflow.models import Variable

#Name of connection added in Secrets Manager
sm_secretId_name = 'airflow/connections/snowflake_accountadmin'
#Secret key region
secret_key_region=Variable.get("sec_key_region")

#Name of connection ID that will be configured in MWAA
snowflake_conn_id = 'snowflake_conn_accountadmin'

#Query to test connection to snowflake
test_query="select distinct ORGANIZATION_NAME from SNOWFLAKE.ORGANIZATION_USAGE.RATE_SHEET_DAILY;"

default_args = {
    'owner': 'airflow',
    'start_date': days_ago(1),
    'snowflake_conn_id': snowflake_conn_id,
    'depends_on_past': False
}

def add_snowflake_connection_callable(**context):
    ### set up Secrets Manager and retrieve variables
    hook = AwsBaseHook(client_type='secretsmanager')
    client = hook.get_client_type(region_name=secret_key_region)
    response = client.get_secret_value(SecretId=sm_secretId_name)
    myConnSecretString = response["SecretString"]
    secrets=json.loads(myConnSecretString)
    logging.info (secrets)  

    ### set up Snowflake connection
    connection: Connection = Connection(
        conn_id=snowflake_conn_id,
        conn_type="snowflake",
        host=secrets['host'],
        login=secrets['user'],
        password=secrets['password'],
        schema=secrets['schema'],
        extra=json.dumps({"extra__snowflake__account": secrets['account'], "extra__snowflake__database": secrets['database'], "extra__snowflake__role": secrets['role'], "extra__snowflake__warehouse": secrets['warehouse']})
    )
    session: Session = settings.Session
    db_connection: Connection = session.query(Connection) \
        .filter(Connection.conn_id == snowflake_conn_id) \
        .first()
    if db_connection is None:
        logging.info("Adding connection: " + snowflake_conn_id)
        session.add(connection)
        session.commit()
    else:
        logging.info("Connection: " + snowflake_conn_id +  " already exists.")

with DAG(
        dag_id=os.path.basename(__file__).replace(".py", ""),
        default_args=default_args,
        dagrun_timeout=timedelta(hours=2),
        start_date=days_ago(1),
        tags=['Snowflake','Citibike', 'DAG1'],
        schedule_interval=None
) as dag:
    add_connection: PythonOperator = PythonOperator(
        task_id="add_snowflake_connection",
        python_callable=add_snowflake_connection_callable
    )

    delay_python_task: PythonOperator = PythonOperator(
        task_id="delay_python_task",
        python_callable=lambda: time.sleep(10)
    )
     
    test_connection = SnowflakeOperator(
        task_id='test_snowflake_connection',
        sql=test_query
    )

add_connection >> delay_python_task >> test_connection
