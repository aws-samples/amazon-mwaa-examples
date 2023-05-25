"""
Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

from airflow import DAG, settings

from airflow.operators.python_operator import PythonOperator
from airflow.operators.dummy import DummyOperator
from airflow.utils.dates import days_ago
from airflow.models import DAG
from airflow.models import Variable, Connection
from airflow.hooks.S3_hook import S3Hook
from sqlalchemy import text
import csv
from io import StringIO
from smart_open import open
import boto3
import json


"""
The module iterates through the list of sql statement and table, reads data and stores in S3 as csv file.
Before it exports the data, it copies all the active dags and pause the execution of all other DAG.
"""
# S3 prefix where the exported file are
S3_KEY = 'data/'

dag_id = 'mwaa_export_data'

DAG_RUN_SELECT = f"select dag_id, execution_date, state, run_id, external_trigger, \
'\\x' || encode(conf,'hex') as conf, end_date,start_date, run_type, last_scheduling_decision, \
 dag_hash, creating_job_id, queued_at, data_interval_start, data_interval_end from dag_run"

TASK_INSTANCE_SELECT = "select task_id, dag_id, run_id, start_date, end_date, duration, state, \
try_number, hostname, unixname, job_id, pool, queue, priority_weight, \
operator, queued_dttm, pid, max_tries, '\\x' || encode(executor_config,'hex') as executor_config ,\
pool_slots, queued_by_job_id, external_executor_id, trigger_id ,\
trigger_timeout, next_method, next_kwargs from task_instance \
where state NOT IN ('running','restarting','queued','scheduled', 'up_for_retry','up_for_reschedule')"


LOG_SELECT = "select dttm, dag_id, task_id, event, execution_date, owner, extra from log"

TASK_FAIL_SELECT = "select task_id, dag_id, execution_date, start_date, end_date, duration from task_fail"


JOB_SELECT = "select dag_id,  state, job_type , start_date, \
end_date, latest_heartbeat, executor_class, hostname, unixname from job"

POOL_SLOTS = "select pool, slots, description from slot_pool where pool != 'default_pool'"
TRIGGER = "select classpath, kwargs, created_date, triggerer_id from trigger"

##################
# Add more tables If you need
##################


# This object contains the statement to select and the table name
# The data is exported to the S3 Bucket defined at the top.

##################
# If you add newer tables, They need an entry here as well
##################

OBJECTS_TO_EXPORT = [
    [DAG_RUN_SELECT, "dag_run"],
    [TASK_INSTANCE_SELECT, "task_instance"],
    [LOG_SELECT, "log"],
    [TASK_FAIL_SELECT, "task_fail"],
    [JOB_SELECT, "job"],
    [TRIGGER, "trigger"],
]


def stream_to_S3_fn(context, result, filename):
    from smart_open import open

    s3_file = f"s3://{get_s3_bucket(context)}/{S3_KEY}{filename}.csv"
    # only get 10K rows at a time
    REC_COUNT = 5000
    outfileStr = ""
    with open(s3_file, 'wb') as write_io:
        while True:
            chunk = result.fetchmany(REC_COUNT)
            if not chunk:
                break
            f = StringIO(outfileStr)
            w = csv.writer(f)
            w.writerows(chunk)
            write_io.write(f.getvalue().encode("utf8"))
        write_io.close()


# pause all active dags to have consistend and reliable copy of dag history exports
def pause_dags():
    session = settings.Session()
    session.execute(
        text(f"update dag set is_paused = true where dag_id != '{dag_id}';"))
    session.commit()
    session.close()


# Exports all active dags to S3; This data is used to unpause the dag in the new environment
def export_active_dags(**context):
    session = settings.Session()
    result = session.execute("select * from active_dags")
    stream_to_S3_fn(context, result, 'active_dags')
    session.close()


# exports variable. Variable value is encrypted;
# So, the method uses the Variable class to decrypt the value and exports the data
def export_variable(**context):
    session = settings.Session()
    s3_hook = S3Hook()
    s3_client = s3_hook.get_conn()
    query = session.query(Variable)
    allrows = query.all()
    k = ["key", "val", "is_encrypted", "description"]
    if len(allrows) > 0:
        outfileStr = ""
        f = StringIO(outfileStr)
        w = csv.DictWriter(f,  k)
        for y in allrows:
            w.writerow({k[0]: y.key, k[1]: y.get_val(),
                       k[2]: y.is_encrypted, k[3]: None})
        outkey = S3_KEY + 'variable.csv'
        s3_client.put_object(Bucket=get_s3_bucket(context), Key=outkey, Body=f.getvalue())
    session.close()

    return "OK"

def export_connection(**context):
    session = settings.Session()
    s3_hook = S3Hook()
    s3_client = s3_hook.get_conn()
    query = session.query(Connection)
    allrows = query.all()
    k = ["conn_id", "conn_type", "host", "schema","login","password","port","extra","is_encrypted","is_extra_encrypted","description"]
    if len(allrows) > 0:
        outfileStr = ""
        f = StringIO(outfileStr)
        w = csv.DictWriter(f,  k)
        for y in allrows:


            w.writerow({k[0]: y.conn_id, k[1]: y.conn_type, k[2]: y.description, k[3]: y.host,
                        k[4]: y.login, k[5]: y.get_password(),k[6]: y.schema, k[7]: y.port,
                        k[8]: y.get_extra()})

        outkey = S3_KEY + 'connection.csv'
        s3_client.put_object(Bucket=get_s3_bucket(context), Key=outkey, Body=f.getvalue())
    session.close()

    return "OK"

# backsup the active dags before pausing them
def back_up_activedags():
    session = settings.Session()
    session.execute(text(f"drop table if exists active_dags;"))
    session.execute(text(
        f"create table active_dags as select dag_id from dag where not is_paused and is_active;"))
    session.commit()
    session.close()

# Activate dags
def activate_dags():
    session = settings.Session()
    conn = settings.engine.raw_connection()
    try:
        session.execute(text(f"UPDATE dag d SET is_paused=false FROM active_dags ed WHERE d.dag_id = ed.dag_id;"))
        session.execute(text(f"drop table active_dags;"))
        session.commit()
    finally:
        conn.close()

# iterate OBJECTS_TO_EXPORT and call export
def export_data(**context):
    session = settings.Session()

    for x in OBJECTS_TO_EXPORT:
        result = session.execute(text(x[0]))
        stream_to_S3_fn(context, result, x[1])

    session.close()
    return "OK"


# Export Failure/Success notification
def get_s3_bucket(context):
    dag_run = context.get('dag_run')
    return dag_run.conf['bucket']


def get_task_token(context):
    dag_run = context.get('dag_run')
    return dag_run.conf['taskToken']


def get_dag_run_result(context):
    dag_run = context.get('dag_run')
    task_instances = dag_run.get_task_instances()
    task_states = []
    for task in task_instances:
        task_states.append(f'{task.task_id} => {task.state}')
    return {'dag': dag_run.dag_id, 'dag_run': dag_run.run_id, 'tasks': task_states}


def notify_success(**context):
    result = get_dag_run_result(context)
    result['location'] = f's3://{get_s3_bucket(context)}/{S3_KEY}'
    result['status'] = 'Success'

    token = get_task_token(context)
    sfn = boto3.client('stepfunctions')
    sfn.send_task_success(taskToken=token, output=json.dumps(result))


def notify_failure(context):
    result = get_dag_run_result(context)
    result['status'] = 'Fail'

    token = get_task_token(context)
    sfn = boto3.client('stepfunctions')
    sfn.send_task_failure(taskToken=token, error='Export Error', cause=json.dumps(result))


default_args = {
    'owner': 'airflow',
    'start_date': days_ago(1),
    'on_failure_callback': notify_failure
}
with DAG(dag_id=dag_id, schedule_interval=None, catchup=False, default_args=default_args) as dag:

    back_up_activedags_t = PythonOperator(
        task_id="back_up_activedags",
        python_callable=back_up_activedags
    )
    pause_dags_t = PythonOperator(
        task_id="pause_dags",
        python_callable=pause_dags
    )
    export_active_dags_t = PythonOperator(
        task_id="export_active_dags",
        python_callable=export_active_dags,
        provide_context=True
    )
    export_variable_t = PythonOperator(
        task_id="export_variable",
        python_callable=export_variable,
        provide_context=True
    )

    export_data_t = PythonOperator(
        task_id="export_data",
        python_callable=export_data,
        provide_context=True
    )
    export_connection_t = PythonOperator(
        task_id="export_connection",
        python_callable=export_connection,
        provide_context=True
    )

    clean_up_t = DummyOperator(task_id='clean_up')

    notify_success_t = PythonOperator(
        task_id='notify_success',
        python_callable=notify_success,
        provide_context=True
    )

    activate_dags_on_failure_t = PythonOperator(
        task_id="activate_dags_on_failure",
        python_callable=activate_dags,
        trigger_rule="one_failed"
    )

    back_up_activedags_t >> pause_dags_t >> [export_data_t, export_active_dags_t, export_variable_t, export_connection_t] >> clean_up_t >> [activate_dags_on_failure_t, notify_success_t]
