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
from airflow.utils.task_group import TaskGroup
import os
import csv
from airflow.models import Variable
# use sleep to slow down CloudWatch queries and avoid throttling issues
from time import sleep
"""
This module imports data in to the table from the data exported by the export script
This iterate through OBJECTS_TO_IMPORT which contains COPY statement and the csv file with data.
This module also copies a configurabled days of task instance log from Cloud Watch

"""
# S3 bucket where the exported file are
S3_BUCKET = Variable.get("S3_BUCKET", default_var='your_s3_bucket')
# S3 prefix where the exported file are
S3_KEY = Variable.get("S3_KEY", default_var='data/migration/2.2.2_to_2.4.3/export/')
# old environment name. Used to export CW log
OLD_ENV_NAME = 'env_2_2_2'
# new environment name. Used to export CW log
NEW_ENV_NAME = 'env_2_4_3'
# Days of task instance log to export; Only for failed state.
TI_LOG_MAX_DAYS = 3

dag_id = 'db_import'

DAG_RUN_IMPORT = "COPY \
dag_run(dag_id, execution_date, state, run_id, external_trigger, \
conf, end_date,start_date, run_type, last_scheduling_decision, \
dag_hash, creating_job_id, queued_at, data_interval_start, data_interval_end, log_template_id) FROM STDIN WITH (FORMAT CSV, HEADER FALSE)"

TASK_INSTANCE_IMPORT = "COPY task_instance(task_id, dag_id, run_id, start_date, end_date, \
duration, state, try_number, hostname, unixname, job_id, pool, \
queue, priority_weight, operator, queued_dttm, pid, max_tries, executor_config,\
pool_slots, queued_by_job_id, external_executor_id, trigger_id , \
trigger_timeout, next_method, next_kwargs, map_index ) FROM STDIN WITH (FORMAT CSV, HEADER FALSE)"

TASK_FAIL_IMPORT = "COPY task_fail(task_id, dag_id, \
 start_date, end_date, duration, map_index, run_id) FROM STDIN WITH (FORMAT CSV, HEADER FALSE)"

JOB_IMPORT = "COPY JOB(dag_id,  state, job_type , start_date, \
end_date, latest_heartbeat, executor_class, hostname, unixname) FROM STDIN WITH (FORMAT CSV, HEADER FALSE)"


LOG_IMPORT = "COPY log(dttm, dag_id, task_id, event, execution_date, owner, extra) FROM STDIN WITH (FORMAT CSV, HEADER FALSE)"
POOL_SLOTS = "COPY slot_pool(pool, slots, description) FROM STDIN WITH (FORMAT CSV, HEADER FALSE)"

OBJECTS_TO_IMPORT = [
    [DAG_RUN_IMPORT, "dag_run.csv"],
    [LOG_IMPORT, "log.csv"],
    [JOB_IMPORT, "job.csv"],
    [POOL_SLOTS, "slot_pool.csv"]
]

# pause all dags before starting import
def pause_dags():
    session = settings.Session()
    session.execute(
        text(f"update dag set is_paused = true where dag_id != '{dag_id}';"))
    session.commit()
    session.close()


def read_s3(filename):
    resource = boto3.resource('s3')
    bucket = resource.Bucket(S3_BUCKET)
    tempfile = f"/tmp/{filename}"
    bucket.download_file(S3_KEY + filename, tempfile)
    return tempfile


def activate_dags():
    session = settings.Session()
    tempfile = read_s3("active_dags.csv")
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

# Gets distinct dag, task and execution date up to the days in TI_LOG_MAX_DAYS for failed state.
# If you need all state, remove the condition from the query  
# Exclude 'dag_id' (import_db) from the query as this does not typically exist in the source environment


def getDagTasks():
    session = settings.Session()
    dagTasks = session.execute(f"select distinct ti.dag_id, ti.task_id, ti.run_id, ti.try_number, date(r.execution_date) as ed \
        from task_instance ti, dag_run r where ti.dag_id <> '{dag_id}' and r.execution_date > current_date - {TI_LOG_MAX_DAYS} and \
            ti.dag_id=r.dag_id and ti.run_id = r.run_id  and ti.state = 'failed' order by ti.dag_id, date(r.execution_date);").fetchall()
    return dagTasks

# Task instance logs are created inside 'airflow-envname-Task' log group. Each instance of the task execution
# creates a log stream. Log streams name forma is changed in 2.4.3. The script will create a new log stream name and adds the logs.
# This function searches for log stream starting with dag, task, execution date in the old environment and copies them to new environment
# This only copies 1 MB of data. For more logs, create code to iterate the get_log_event using next_token


def create_logstreams():

    client = boto3.client('logs')
    dagTasks = getDagTasks()
    oldlogGroupName = f"airflow-{OLD_ENV_NAME}-Task"
    logGroupName = f"airflow-{NEW_ENV_NAME}-Task"
    logEventFieds = ['timestamp', 'message']

    dagTasksCount = len(dagTasks)
    print(f"Obtaining logs for {dagTasksCount} Log Groups")

    for i,row in enumerate(dagTasks):
        prefix = row['dag_id']+"/"+row['task_id'] + \
            "/" + row["ed"].strftime('%Y-%m-%d')
        # prefix search logs
        sleep(2)
        print(f"Getting LogStreams #{i} of {dagTasksCount} - {prefix=}")
        streams = client.describe_log_streams(
            logGroupName=oldlogGroupName,
            logStreamNamePrefix=prefix,
        )
        logStreamsCount = len(streams['logStreams'])
        print(f"Obtaining events for {logStreamsCount} Log Streams")

        for streamNum,item in enumerate(streams['logStreams']):
            streamName = item["logStreamName"]
            runid = row['run_id'].replace(":","_")
            newStreamName = "dag_id="+row['dag_id']+"/run_id=" + runid + \
            "/task_id=" + row["task_id"] + "/attempt=" + str(row['try_number'])+".log"
            print(f"Copying {streamName} to {newStreamName} - {streamNum} of {logStreamsCount}")
            try:
                # Get log events from old environment max of 1MB
                events = client.get_log_events(
                    logGroupName=oldlogGroupName,
                    logStreamName=streamName,
                    startFromHead=True
                )
                # Put log events in new environment
                oldLogEvents = events["events"]
                oldLogEventsCount = len(oldLogEvents)
                if len(oldLogEvents) > 0:
                    print(f"Adding {oldLogEventsCount} to {newStreamName}")
                    try:
                        client.create_log_stream(
                            logGroupName=logGroupName,
                            logStreamName=newStreamName
                        )
                    except:
                        print(f"{newStreamName} existed - recreating")
                        client.delete_log_stream(
                            logGroupName=logGroupName,
                            logStreamName=newStreamName
                        )
                        client.create_log_stream(
                            logGroupName=logGroupName,
                            logStreamName=newStreamName
                        )

                    eventsToInjest = []
                    for item in oldLogEvents:
                        newItem = {key: value for key,
                                   value in item.items() if key in logEventFieds}
                        eventsToInjest.append(newItem)

                    client.put_log_events(
                        logGroupName=logGroupName,
                        logStreamName=newStreamName,
                        logEvents=eventsToInjest
                    )

            except Exception as e:
                print("Exception occured ", e)


# variables are imported separately as they are encyrpted
def importVariable():
    # If there were no variables in the source environment the variable.csv file may not exist
    try:
        tempfile = read_s3('variable.csv')
    except:
        print("variable.csv file not present or not accessible")
        return
    
    session = settings.Session()

    with open(tempfile, 'r') as csvfile:
        reader = csv.reader(csvfile)
        rows = []
        for row in reader:
            rows.append(Variable(row[0], row[1]))
        if len(rows) > 0:
            session.add_all(rows)
    session.commit()
    session.close()


def load_data(**kwargs):
    query = kwargs['query']
    tempfile = read_s3(kwargs['file'])
    conn = settings.engine.raw_connection()
    try:
        with open(tempfile, 'r') as f:
            cursor = conn.cursor()
            cursor.copy_expert(query, f)
            conn.commit()
    except Exception as e:
        print("Exception:",e)
    finally:
        conn.close()
        os.remove(tempfile)


with DAG(dag_id=dag_id, schedule_interval=None, catchup=False, start_date=days_ago(1)) as dag:

    pause_dags_t = PythonOperator(
        task_id="pause_dags",
        python_callable=pause_dags
    )
    with TaskGroup(group_id='import') as import_t:
        for x in OBJECTS_TO_IMPORT:
            load_task = PythonOperator(
                task_id=x[1],
                python_callable=load_data,
                op_kwargs={'query': x[0], 'file': x[1]},
                provide_context=True
            )
    load_variable_t = PythonOperator(
        task_id="variable",
        python_callable=importVariable
    )

    load_task_instance_t = PythonOperator(
        task_id="load_ti",
        op_kwargs={'query': TASK_INSTANCE_IMPORT, 'file': 'task_instance.csv'},
        provide_context=True,
        python_callable=load_data
    )
    load_task_instance_fail_t = PythonOperator(
        task_id="load_ti_fail",
        op_kwargs={'query': TASK_FAIL_IMPORT, 'file': 'task_fail.csv'},
        provide_context=True,
        python_callable=load_data
    )
    load_CW_logs = PythonOperator(
        task_id="load_CW_logs",
        python_callable=create_logstreams
    )
    # activate_dags_t = PythonOperator(
    #     task_id="activate_dags",
    #     python_callable=activate_dags
    # )
    pause_dags_t >> import_t >> load_task_instance_t >> load_task_instance_fail_t 
    # load_CW_logs >> activate_dags_t
    load_task_instance_t >> load_CW_logs
    load_task_instance_t >> load_variable_t