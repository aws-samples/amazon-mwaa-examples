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


from airflow import DAG
from airflow.operators.python_operator import PythonOperator
from airflow.operators.python_operator import BranchPythonOperator

from airflow.utils.dates import days_ago
from datetime import datetime, timedelta
from airflow.operators.dummy_operator import DummyOperator
from airflow.operators.bash_operator import BashOperator
from airflow.contrib.hooks.aws_lambda_hook import AwsLambdaHook
from airflow.contrib.hooks.aws_dynamodb_hook import AwsDynamoDBHook
import boto3

import json


args = {
    'owner': 'airflow',
}
def face_detection(ds, **kwargs): 
    client = boto3.client('rekognition')
    arg = kwargs['dag_run'].conf
    print(arg)
    print(kwargs['dag_run'])
    try:
        response = client.detect_faces(
            Image={
                'S3Object': {
                    'Bucket': arg['s3Bucket'],
                    'Name': arg['s3Key'],
                }
            },
            Attributes=['ALL']
        )
        print(response)
        if len(response['FaceDetails']) != 1:
            return "photo_not_meet_requirement"
        if response['FaceDetails'][0]['Sunglasses']['Value']:
            return "photo_not_meet_requirement"

        kwargs['ti'].xcom_push(key="FaceDetails", value=response['FaceDetails'][0])
        return "check_duplicate"
    except Exception as e:
        print(e)
        return "failure"

def check_duplicate(ds, **kwargs): 

    client = boto3.client('rekognition')
    arg = kwargs['dag_run'].conf
    try:
        response = client.search_faces_by_image(
        
            CollectionId=arg['RekognitionCollectionId'],
            Image={
                "S3Object": {
                    "Bucket": arg['s3Bucket'],
                    "Name": arg['s3Key']
                }
            },
            FaceMatchThreshold=70.0,
            MaxFaces=3
            
        )
        print(response)
        if len(response['FaceMatches']) > 0: #Face already exist
            return "duplicate_face"
        return "parallel_processing"
        # kwargs['ti'].xcom_push(key="FaceDetails", value=response.FaceDetails[0])
    except  Exception as e: 
        print(e)
        return "failure"

def create_thumbnail(ds, **kwargs): 

    hook = AwsLambdaHook('LAMBDA_FN_NAME', #LAMBDA_FN_NAME
                            log_type='None',qualifier='$LATEST',
                            invocation_type='RequestResponse',
                            config=None,aws_conn_id='aws_default')

    response_1 = hook.invoke_lambda(payload=json.dumps(kwargs['dag_run'].conf))
    payload = json.loads(response_1['Payload'].read().decode())
    kwargs['ti'].xcom_push(key="ThumbnailDetails", value=payload)

def add_face_index(ds, **kwargs): 
    client = boto3.client('rekognition')
    arg = kwargs['dag_run'].conf

    
    response = client.index_faces(
        CollectionId=arg['RekognitionCollectionId'],
        DetectionAttributes=['ALL'],
        ExternalImageId=arg['userId'],
        Image={
            "S3Object": {
                "Bucket": arg['s3Bucket'],
                "Name": arg['s3Key']
            }
        }

    )
    print(response['FaceRecords'][0])
    kwargs['ti'].xcom_push(key="FaceIndexDetails", value=response['FaceRecords'][0]['Face'])


def persist_data( **kwargs): 
    hook = AwsDynamoDBHook(table_name="TABLE_NAME", #TABLE_NAME
                            aws_conn_id='aws_default')
    faceIndexDetails = kwargs['ti'].xcom_pull(key='FaceIndexDetails')
    thumbnailDetails = kwargs['ti'].xcom_pull(key='ThumbnailDetails')
    conf = kwargs['dag_run'].conf
    dynamoItem = {
        "UserId" : conf["userId"],
        "s3Bucket" : conf["s3Bucket"],
        "s3Key": conf["s3Key"],
        "faceId" :faceIndexDetails['FaceId'],
        "thumbnail": thumbnailDetails['thumbnail']    
    }
    items = [dynamoItem]
    hook.write_batch_data(items)


dag_args = {
    'owner': 'simple airflow',
    'depends_on_past': False,
    'email': ['airflow@example.com'],
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=1)}
dag =  DAG(
    dag_id='image_processing',
    start_date=days_ago(2),
    default_args=dag_args,
    end_date=None,
    schedule_interval=None,
    # schedule_interval='0 9 * * *',
    tags=['lambda','imageprocessing'])

# arg = json.dumps(kwargs['dag_run'].conf
# print(arg)
face_detection = BranchPythonOperator(
    depends_on_past=False,
    task_id='face_detection',
    python_callable=face_detection,
    provide_context=True,
    xcom_push=True,
    dag=dag,
)

# [START howto_operator_bash]
photo_not_meet_requirement = BashOperator(
    task_id='photo_not_meet_requirement',
    bash_command='echo photo_not_meet_requirement',
    dag=dag,
)
check_duplicate = BranchPythonOperator(
    task_id='check_duplicate',
    python_callable=check_duplicate,
    provide_context=True,
    xcom_push=True,
    dag=dag,
)
duplicate_face = BashOperator(
    task_id='duplicate_face',
    bash_command='echo duplicate_face',
    dag=dag,
)
failure = BashOperator(
    task_id='failure',
    bash_command='echo failure',
    dag=dag,
)

parallel_processing = DummyOperator(
    task_id='parallel_processing',
    dag=dag,
)
add_face_index = PythonOperator(
    task_id='add_face_index',
    python_callable=add_face_index,
    provide_context=True,
    xcom_push=True,
    dag=dag,
)
create_thumbnail = PythonOperator(
    task_id='create_thumbnail',
    python_callable=create_thumbnail,
    provide_context=True,
    xcom_push=True,
    dag=dag,
)
persist_data = PythonOperator(
    task_id='persist_data',
    python_callable=persist_data,
    provide_context=True,
    dag=dag,
)


face_detection >> [photo_not_meet_requirement, check_duplicate, failure] 
check_duplicate >> [duplicate_face, failure, parallel_processing]
parallel_processing >> add_face_index >> persist_data
parallel_processing >> create_thumbnail >> persist_data


if __name__ == "__main__":
    dag.cli()
