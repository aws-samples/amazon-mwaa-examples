### Move your Apache Airflow Connections and Variables to AWS Secrets Manager

This example reads from an existing Metadatabase and copies all connections and variables to AWS Secrets Manager

### Setup 

Copy the file into your DAGs folder, and ensure you have connectivity to AWS Secrets Manager. For the latter, When using an AWS IAM role to connect to AWS Secrets Manager, either with Amazon MWAA’s Execution Role or an assumed role in Amazon EC2, you will need to provide AWS Secrets Manager access to that role via the [AWS IAM console](https://console.aws.amazon.com/iam/home#/roles).

### Requirements.txt needed

None.

### Plugins needed 

None.

### Explanation

The first thing we’ll do is set up our DAG and imports:

```
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
```
We’ll then create a function that will use a secretsmanager boto3 client to add/update a given key to secrets manager.  As create and update are separate calls, we’re trying the former and if it fails we’ll assume that the secret already exists and just needs to be updated:

```
def write_to_sm_fn(name,value,client):
    print("Writing ",name,"=",value,"to AWS Secrets Manager...")
    try:
        response = client.create_secret(Name=name,SecretString=value)
    except:
        print(name," exists, overwriting...")
        response = client.put_secret_value(SecretId=name,SecretString=value)

    print(response)    

```
The main function that our PythonOperator will call starts by determining the correct secrets prefixes to use by querying the backend_kwargs defined for our environment:
```
def write_all_to_aws_sm_fn(**kwargs):
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
```
We’ll then create a secretsmanager boto3 client using AwsHook, and a SQLAlchemy session to populate the Connection and Variable models:
```
    session = settings.Session()
    hook = AwsHook()
    client = hook.get_client_type('secretsmanager')
```
We’ll now query and create the entries for the Connections defined in our Apache Airflow environment. To make things easier, Apache Airflow provides a utility function get_uri()to generate a connection string from a Connection object.  We can use airflow.models.Connection along with SQLAlchemy to get a list of Connection objects that we can convert to URIs, and then use boto3 to push these to AWS Secrets Manager.
```
    query = session.query(Connection)
    print(query.count()," connections: ")   
    for curr_entry in query:
        curr_id=connections_prefix+'/'+curr_entry.conn_id
        curr_val=curr_entry.get_uri()
        write_to_sm_fn(name=curr_id, value=curr_val, client=client)
```
We can use a similar method to retrieve a list of Variable objects, then use Variable.get() to retrieve the values and push them also via boto3. After that we’ll return from the function.
```
    query = session.query(Variable)
    print(query.count()," variables: ")   
    for curr_entry in query:
        curr_id=variables_prefix+'/'+curr_entry.key
        curr_val=curr_entry.get_val()
        write_to_sm_fn(name=curr_id, value=curr_val, client=client)

    return "OK"
```
The DAG itself is just a host for the PythonOperator that calls the above function.
```
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
```
## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the LICENSE file.

