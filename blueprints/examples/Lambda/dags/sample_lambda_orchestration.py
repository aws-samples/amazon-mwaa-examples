from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
from retry import retry
from custom_libraries.Lambda.hooks.lambda_function import LambdaHook
from custom_libraries.Lambda.operators.lambda_function import AwsLambdaInvokeFunctionOperator
from custom_libraries.Lambda.sensors.lambda_function import LambdaStateSensor
import json
import time
import os

S3Bucket = "my-custom-data-source-destination-bucket"
region=os.environ['AWS_DEFAULT_REGION']

lambdacode = {
    'ImageUri': f"123456789.dkr.ecr.{region}.amazonaws.com/taxi_analysis:latest",
}

lambda_role = f'arn:aws:iam::123456789:role/taxi_ride_analysis_lambda_execution_role'

taxi = ['yellow', 'green', 'fhv']
year = '2022'
project = 'taxi_ride_analysis'

def getData(taxiname, year, month):
    import requests
    import boto3

    filename = f'{taxiname}_tripdata_{year}-{month}.parquet'
    url = f'https://d37ci6vzurychx.cloudfront.net/trip-data/{filename}'
    print(url)
    r = requests.get(url, allow_redirects=True)

    s3 = boto3.resource('s3', region_name=region)
    s3.Object(
        S3Bucket, f'input/data/{year}/{month}/{taxiname}_tripdata.parquet').put(Body=r.content)


@retry(delay=3, tries=3)
def createLambdaFunction(function_name, lambda_role):
    hook = LambdaHook(aws_conn_id='aws_default',
                      region_name=region, config=None,)

    hook.create_lambda(function_name=function_name,
                       timeout=15*60,
                       memory_size=2048,
                       role=lambda_role,
                       package_type='Image',
                       code=lambdacode)

def deleteLambdaFunction(name, qualifier):
    hook = LambdaHook(aws_conn_id='aws_default',
                      region_name=region, config=None,)
    hook.delete_lambda(function_name=name)

def create_dag(dag_id,
               taxiname,
               schedule,
               default_args):

    months = ['01', '02', '03', '04', '05', '06']
    lambda_name = f'{project}_{taxiname}'

    dag = DAG(dag_id,
              schedule_interval=None,
              catchup=False,
              default_args=default_args)

    with dag:
        
        create_lambda = PythonOperator(
            task_id="create_lambda",
            python_callable=createLambdaFunction,
            op_kwargs={'function_name': lambda_name,
                       'lambda_role': lambda_role},
            provide_context=True
        )

        delete_lambda = PythonOperator(
            task_id="delete_lambda",
            python_callable=deleteLambdaFunction,
            op_kwargs={'name': lambda_name, 'qualifier': '$LATEST'},
            provide_context=True
        )

        lambda_state_sensor = LambdaStateSensor(
                task_id=f'sense_lambda',
                function_name=lambda_name,
                qualifier='$LATEST',
                aws_conn_id='aws_default',
                poke_interval=30,
                timeout=60 * 2)
        
        for month in months:
            source_data = PythonOperator(
                task_id=f'source_data_{month}',
                python_callable=getData,
                op_kwargs={'taxiname': taxiname, 'year': year, 'month': month},
                provide_context=True
            )

            event_payload = {'bucket': f'{S3Bucket}',
                             'key': f'input/data/{year}/{month}/{taxiname}_tripdata.parquet'}
            invoke_lambda = AwsLambdaInvokeFunctionOperator(
                function_name=lambda_name,
                task_id=f'invoke_lambda_{month}',
                qualifier='$LATEST',
                invocation_type='RequestResponse',
                payload=json.dumps(event_payload),
                aws_conn_id='aws_default'
            )

            

            source_data >> invoke_lambda
            lambda_state_sensor >> invoke_lambda >> delete_lambda    

        create_lambda >> lambda_state_sensor
        #delete_lambda

    return dag


i = 0
for taxiname in taxi:
    print(taxiname[0])
    dag_no = i + 1
    dag_id = 'tripreport_{}'.format(taxiname)
    default_args = {'owner': 'airflow',
                    'start_date': datetime.now()
                    }

    globals()[dag_id] = create_dag(dag_id,
                                   taxiname,
                                   None,
                                   default_args
                                   )
