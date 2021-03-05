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

from airflow import DAG, settings, secrets
from airflow.operators.python_operator import PythonOperator
from airflow.utils.dates import days_ago
from airflow.models import Connection, Variable
from airflow.contrib.hooks.aws_hook import AwsHook

from datetime import timedelta
import os
import json

DEFAULT_ARGS = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email': ['airflow@example.com'],
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 0,
}

### write_to_sm_fn writes/overwrites an individual value in AWS Secrets Manager
def write_to_sm_fn(name,value,client):
    print("Writing ",name,"=",value,"to AWS Secrets Manager...")
    try:
        response = client.create_secret(Name=name,SecretString=value)
    except:
        print(name," exists, overwriting...")
        response = client.put_secret_value(SecretId=name,SecretString=value)

    print(response)    

### write_all_to_aws_sm_fn transfers all connections and variables to AWS Secrets Manager
def write_all_to_aws_sm_fn(**kwargs):
    ### determine secrets manager prefixes
    connections_prefix='airflow/connections'
    variables_prefix='airflow/variables'
    backend_kwargs = kwargs['conf'].get(section='secrets', key='backend_kwargs')
    if backend_kwargs:
        x = json.loads(backend_kwargs)
        connections_prefix=x['connections_prefix'].strip().rstrip('/')
        variables_prefix=x['variables_prefix'].strip().rstrip('/')
        print("using connections_prefix=",connections_prefix,",variables_prefix=",variables_prefix,"...")
    else: 
        print("backend_kwargs undefined--using defaults connections_prefix=",connections_prefix,",variables_prefix=",variables_prefix)

    ### set up SQL and AWSSM
    session = settings.Session()
    hook = AwsHook()
    client = hook.get_client_type('secretsmanager')

    ### transfer connections
    query = session.query(Connection)
    print(query.count()," connections: ")   
    for curr_entry in query:
        curr_id=connections_prefix+'/'+curr_entry.conn_id
        curr_val=curr_entry.get_uri()
        write_to_sm_fn(name=curr_id, value=curr_val, client=client)

    ### transfer variables
    query = session.query(Variable)
    print(query.count()," variables: ")   
    for curr_entry in query:
        curr_id=variables_prefix+'/'+curr_entry.key
        curr_val=curr_entry.get_val()
        write_to_sm_fn(name=curr_id, value=curr_val, client=client)

    return "OK"

with DAG(
    dag_id=os.path.basename(__file__).replace(".py", ""),
    default_args=DEFAULT_ARGS,
    dagrun_timeout=timedelta(hours=2),
    start_date=days_ago(1),
    schedule_interval=None
) as dag:

    write_all_to_aws_sm = PythonOperator(
        task_id="write_all_to_aws_sm",
        python_callable=write_all_to_aws_sm_fn,
        provide_context=True     
    )
