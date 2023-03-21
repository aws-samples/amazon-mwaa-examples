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
from airflow.utils.dates import days_ago
from airflow.models import DAG, DagRun, TaskFail, TaskInstance, Log
from airflow.models import Variable, Connection
from airflow.hooks.S3_hook import S3Hook
from sqlalchemy import text
import csv
import re
from io import StringIO
from smart_open import open
import tempfile

"""
The module iterates through the list of sql statement and table, reads data and stores in S3 as csv file.
Before it exports the data, it copies all the active dags and pause the execution of all other DAG.
"""
# S3 bucket where the exported file are
S3_BUCKET = Variable.get("S3_BUCKET", default_var='your_s3_bucket')
# S3 prefix where the exported file are
S3_KEY = Variable.get("S3_KEY", default_var='data/migration/2.2.2_to_2.4.3/export/')

dag_id = 'db_export'


DAG_RUN_SELECT = f"select dag_id, execution_date, state, run_id, external_trigger, \
'\\x' || encode(conf,'hex') as conf, end_date,start_date, run_type, last_scheduling_decision, \
 dag_hash, creating_job_id, null as queued_at, null as data_interval_start, null as data_interval_end, \
 2 as log_template_id  from dag_run where dag_id != '{dag_id}'"

TASK_INSTANCE_SELECT = f"select task_id, dag_id,  run_id  , start_date, end_date, duration, state, \
try_number, hostname, unixname, job_id, pool, queue, priority_weight, \
operator, queued_dttm, pid, max_tries, '\\x' || encode(ti.executor_config,'hex') as executor_config ,\
pool_slots, queued_by_job_id, external_executor_id, trigger_id ,\
trigger_timeout, next_method, next_kwargs, -1 as map_index \
 from task_instance ti where dag_id != '{dag_id}'"


LOG_SELECT = "select dttm, dag_id, task_id, event, execution_date, owner, extra from log"

TASK_FAIL_SELECT = "select tf.task_id, tf.dag_id, \
 tf.start_date, tf.end_date, tf.duration, -1 as map_index, r.run_id from task_fail tf,  dag_run r where r.dag_id = tf.dag_id AND \
  r.execution_date = tf.execution_date"

JOB_SELECT = "select dag_id,  state, job_type , start_date, \
end_date, latest_heartbeat, executor_class, hostname, unixname from job"

POOL_SLOTS = "select pool, slots, description from slot_pool where pool != 'default_pool'"


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
    [POOL_SLOTS, "slot_pool"],

]


def stream_to_S3_fn(result, filename):
    s3_file = f"s3://{S3_BUCKET}/{S3_KEY}{filename}.csv"
    # only get 10K rows at a time
    REC_COUNT = 1000
    
    with tempfile.NamedTemporaryFile() as tmp:
        tp = {'writebuffer': tmp}
        with open(s3_file, 'wb', transport_params=tp) as write_io:
            while True:
                chunk = result.fetchmany(REC_COUNT)
                if not chunk:
                    break
                outfileStr = ""
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


def export_active_dags():
    session = settings.Session()
    result = session.execute("select * from active_dags")
    stream_to_S3_fn(result, 'active_dags')
    session.close()

# exports variable. Variable value is encrypted;
# So, the method uses the Variable class to decrypt the value and exports the data


def export_variable():
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
        s3_client.put_object(Bucket=S3_BUCKET, Key=outkey, Body=f.getvalue())
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

# iterate OBJECTS_TO_EXPORT and call export


def export_data(**kwargs):
    session = settings.Session()
    for x in OBJECTS_TO_EXPORT:
        result = session.execute(text(x[0]))
        stream_to_S3_fn(result, x[1])

    session.close()

    return "OK"


with DAG(dag_id=dag_id, schedule_interval=None, catchup=False, start_date=days_ago(1)) as dag:

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
        python_callable=export_active_dags
    )
    export_variable_t = PythonOperator(
        task_id="export_variable",
        python_callable=export_variable
    )

    export_data_t = PythonOperator(
        task_id="export_data",
        python_callable=export_data,
        provide_context=True
    )
    # backup all active dag; pause the dags; export all the tables in the OBJECTS_TO_EXPORT;
    # export the active dags so they can be turned on in the new environment
    # Export variables.
    back_up_activedags_t >> pause_dags_t >> export_data_t
    pause_dags_t >> export_active_dags_t
    pause_dags_t >> export_variable_t
