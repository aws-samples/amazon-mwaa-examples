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

from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago
from sqlalchemy import text
import boto3
import botocore
from airflow.utils.task_group import TaskGroup
import os
import csv
from airflow.models import Variable,Connection
import json

"""
This module imports data in to the table from the data exported by the export script
This iterate through OBJECTS_TO_IMPORT which contains COPY statement and the csv file with data.
This module also copies a configurabled days of task instance log from Cloud Watch

"""
# S3 prefix to look for exported data
S3_KEY = 'data/'

dag_id = 'mwaa_import_data'

DAG_RUN_IMPORT = "COPY \
dag_run(dag_id, clear_number, execution_date, state, run_id, external_trigger, \
conf, end_date,start_date, run_type, last_scheduling_decision, \
dag_hash, creating_job_id, queued_at, data_interval_start, data_interval_end, log_template_id, updated_at) FROM STDIN WITH (FORMAT CSV, HEADER FALSE)"

TASK_INSTANCE_IMPORT = "COPY task_instance(task_id, dag_id, run_id, custom_operator_name, start_date, end_date, \
duration, state, task_display_name, try_number, hostname, unixname, job_id, pool, \
queue, priority_weight, operator, queued_dttm, rendered_map_index, pid, max_tries, executor_config,\
pool_slots, queued_by_job_id, external_executor_id, trigger_id , \
trigger_timeout, next_method, next_kwargs, map_index, updated_at) FROM STDIN WITH (FORMAT CSV, HEADER FALSE)"

TASK_FAIL_IMPORT = "COPY task_fail(task_id, dag_id, run_id, map_index, \
 start_date, end_date, duration) FROM STDIN WITH (FORMAT CSV, HEADER FALSE)"


JOB_IMPORT = "COPY JOB(dag_id,  state, job_type , start_date, \
                end_date, latest_heartbeat, executor_class, hostname, unixname) \
                FROM STDIN WITH (FORMAT CSV, HEADER FALSE)"


LOG_IMPORT = "COPY log(dttm, dag_id, task_id, event, execution_date, owner, owner_display_name, run_id, extra) FROM STDIN WITH (FORMAT CSV, HEADER FALSE)"
POOL_SLOTS = "COPY slot_pool(pool, slots, description, include_deferred) FROM STDIN WITH (FORMAT CSV, HEADER FALSE)"
TRIGGER = "COPY trigger(classpath, kwargs, created_date, triggerer_id)\
             FROM STDIN WITH (FORMAT CSV, HEADER FALSE)"

# Starting in v2.9.2, we are exculing dataset tables from imports as they are auto-generated
OBJECTS_TO_IMPORT = [
    [DAG_RUN_IMPORT, "dag_run.csv"],
    [LOG_IMPORT, "log.csv"],
    [JOB_IMPORT, "job.csv"],
    [POOL_SLOTS, "slot_pool.csv"],
]

# pause all dags before starting export
def pause_dags():
    session = settings.Session()
    session.execute(text(f"update dag set is_paused = true where dag_id != '{dag_id}';"))
    session.commit()
    session.close()

def read_s3(context, filename):
    resource = boto3.resource('s3')
    bucket = resource.Bucket(get_s3_bucket(context))
    tempfile = f"/tmp/{filename}"
    try:
        bucket.download_file(S3_KEY + filename, tempfile)
    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] == "404":
            return None
        else:
            raise
    else:
        return tempfile


def activate_dags(**context):
    session = settings.Session()
    tempfile = read_s3(context, "active_dags.csv")
    if (not tempfile):
        return

    conn = settings.engine.raw_connection()
    try:
        session.execute(
            text(f"create table if not exists active_dags(dag_id varchar(250))"))
        session.commit()
        with open(tempfile, 'r') as f:
            cursor = conn.cursor()
            cursor.copy_expert(
                "COPY active_dags FROM STDIN WITH (FORMAT CSV, HEADER TRUE)", f)
            conn.commit()
        session.execute(text(
            f"UPDATE dag d SET is_paused=false FROM active_dags ed WHERE d.dag_id = ed.dag_id;"))
        session.commit()
    finally:
        conn.close()

# Variables are imported separately as they are encyrpted
def importVariable(**context):
    session = settings.Session()
    tempfile = read_s3(context, 'variable.csv')
    if (not tempfile):
        return

    with open(tempfile, 'r') as csvfile:
        reader = csv.reader(csvfile)
        rows = []
        for row in reader:
            rowexist = session.query(Variable).filter(Variable.key==row[0]).all()
            if (len(rowexist)==0):
                rows.append(Variable(row[0], row[1]))
            else:
                print(f"Already Exists Varible {list(rowexist)}")
        if len(rows) > 0:
            session.add_all(rows)
    session.commit()
    session.close()


def importConnection(**context):
    session = settings.Session()
    tempfile = read_s3(context, 'connection.csv')
    if (not tempfile):
        return

    with open(tempfile, 'r') as csvfile:
        reader = csv.reader(csvfile)
        rows = []
        for row in reader:
            rowexist = session.query(Connection).filter(Connection.conn_id==row[0]).all()
            if(len(rowexist) == 0):
                port = 0
                if(len(row[7]) > 0):
                    port = int(row[7])
                rows.append(Connection(row[0], row[1],row[2], row[3],row[4],
                             row[5],row[6], port,row[8]))

        if len(rows) > 0:
            session.add_all(rows)
    session.commit()
    session.close()


def load_data(**context):
    query = context['query']
    tempfile = read_s3(context, context['file'])
    if (not tempfile):
        return

    conn = settings.engine.raw_connection()
    try:
        with open(tempfile, 'r') as f:
            cursor = conn.cursor()
            cursor.copy_expert(query, f)
            conn.commit()
    finally:
        conn.close()
        os.remove(tempfile)


# Export Failure/Success notification functions
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
    sfn.send_task_failure(
        taskToken=token, error='Import Error', cause=json.dumps(result))


default_args = {
    'owner': 'airflow',
    'start_date': days_ago(1),
    'on_failure_callback': notify_failure
}
with DAG(dag_id=dag_id, schedule_interval=None, catchup=False,  default_args=default_args) as dag:

    pause_dags_t = PythonOperator(
        task_id="pause_dags",
        python_callable=pause_dags
    )
    with TaskGroup(group_id='toplevel_tables') as import_t:
        for x in OBJECTS_TO_IMPORT:
            load_task = PythonOperator(
                task_id=x[1],
                python_callable=load_data,
                op_kwargs={'query': x[0], 'file': x[1]},
                provide_context=True
            )
        load_variable_t = PythonOperator(
            task_id="variable",
            python_callable=importVariable,
            provide_context=True
        )
        load_connection_t = PythonOperator(
            task_id="connection",
            python_callable=importConnection,
            provide_context=True
        )

    pause_dags_t >> import_t
    load_task_instance = PythonOperator(
        task_id="load_ti",
        op_kwargs={'query': TASK_INSTANCE_IMPORT, 'file': 'task_instance.csv'},
        python_callable=load_data,
        provide_context=True
    )
    load_triggers = PythonOperator(
        task_id="load_trg",
        op_kwargs={'query': TRIGGER, 'file': 'trigger.csv'},
        python_callable=load_data,
        provide_context=True
    )
    import_t >> load_triggers >> load_task_instance

    taskfail_dagrun = PythonOperator(
        task_id="task_fail_run",
        op_kwargs={'query': TASK_FAIL_IMPORT, 'file': 'task_fail.csv'},
        python_callable=load_data,
        provide_context=True
    )
    load_task_instance >> taskfail_dagrun

    activate_dags_t = PythonOperator(
        task_id="activate_dags",
        python_callable=activate_dags,
        provide_context=True
    )
    load_task_instance >> activate_dags_t

    notify_success_t = PythonOperator(
        task_id='notify_success',
        python_callable=notify_success,
        provide_context=True
    )
    activate_dags_t >> notify_success_t
    taskfail_dagrun >> notify_success_t
