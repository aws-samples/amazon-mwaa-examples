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


import json
from datetime import timedelta

import boto3
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.dummy import DummyOperator
from airflow.operators.python import BranchPythonOperator, PythonOperator
from airflow.providers.amazon.aws.hooks.dynamodb import AwsDynamoDBHook
from airflow.providers.amazon.aws.hooks.lambda_function import AwsLambdaHook
from airflow.utils.dates import days_ago

args = {
    "owner": "airflow",
}


def face_detection(ds, **kwargs):
    client = boto3.client("rekognition")
    arg = kwargs["dag_run"].conf
    print(arg)
    print(kwargs["dag_run"])
    try:
        response = client.detect_faces(
            Image={
                "S3Object": {
                    "Bucket": arg["s3Bucket"],
                    "Name": arg["s3Key"],
                }
            },
            Attributes=["ALL"],
        )
        print(response)
        if len(response["FaceDetails"]) != 1:
            return "photo_not_meet_requirement"
        if response["FaceDetails"][0]["Sunglasses"]["Value"]:
            return "photo_not_meet_requirement"

        kwargs["ti"].xcom_push(key="FaceDetails", value=response["FaceDetails"][0])
        return "check_duplicate"
    except Exception as e:
        print(e)
        return "failure"


def check_duplicate(ds, **kwargs):

    client = boto3.client("rekognition")
    arg = kwargs["dag_run"].conf
    try:
        response = client.search_faces_by_image(
            CollectionId=arg["RekognitionCollectionId"],
            Image={"S3Object": {"Bucket": arg["s3Bucket"], "Name": arg["s3Key"]}},
            FaceMatchThreshold=70.0,
            MaxFaces=3,
        )
        print(response)
        if len(response["FaceMatches"]) > 0:  # Face already exist
            return "duplicate_face"
        return "parallel_processing"
        # kwargs['ti'].xcom_push(key="FaceDetails", value=response.FaceDetails[0])
    except Exception as e:
        print(e)
        return "failure"


def create_thumbnail(ds, **kwargs):
    ssm = boto3.client("ssm")
    parameter = ssm.get_parameter(Name="/mwaa-image-processing/LAMBDA_FN_NAME")
    function_name = parameter["Parameter"]["Value"]
    hook = AwsLambdaHook(
        function_name,
        log_type="None",
        qualifier="$LATEST",
        invocation_type="RequestResponse",
        config=None,
        aws_conn_id="aws_default",
    )

    response_1 = hook.invoke_lambda(payload=json.dumps(kwargs["dag_run"].conf))
    payload = json.loads(response_1["Payload"].read().decode())
    kwargs["ti"].xcom_push(key="ThumbnailDetails", value=payload)


def add_face_index(ds, **kwargs):
    client = boto3.client("rekognition")
    arg = kwargs["dag_run"].conf

    response = client.index_faces(
        CollectionId=arg["RekognitionCollectionId"],
        DetectionAttributes=["ALL"],
        ExternalImageId=arg["userId"],
        Image={"S3Object": {"Bucket": arg["s3Bucket"], "Name": arg["s3Key"]}},
    )
    print(response["FaceRecords"][0])
    kwargs["ti"].xcom_push(
        key="FaceIndexDetails", value=response["FaceRecords"][0]["Face"]
    )


def persist_data(**kwargs):
    ssm = boto3.client("ssm")
    parameter = ssm.get_parameter(Name="/mwaa-image-processing/TABLE_NAME")
    table_name = parameter["Parameter"]["Value"]
    hook = AwsDynamoDBHook(table_name=table_name, aws_conn_id="aws_default")
    faceIndexDetails = kwargs["ti"].xcom_pull(key="FaceIndexDetails")
    thumbnailDetails = kwargs["ti"].xcom_pull(key="ThumbnailDetails")
    conf = kwargs["dag_run"].conf
    dynamoItem = {
        "UserId": conf["userId"],
        "s3Bucket": conf["s3Bucket"],
        "s3Key": conf["s3Key"],
        "faceId": faceIndexDetails["FaceId"],
        "thumbnail": thumbnailDetails["thumbnail"],
    }
    items = [dynamoItem]
    hook.write_batch_data(items)


dag_args = {
    "owner": "simple airflow",
    "depends_on_past": False,
    "email": ["airflow@example.com"],
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=1),
}
dag = DAG(
    dag_id="image_processing",
    start_date=days_ago(2),
    default_args=dag_args,
    end_date=None,
    schedule_interval=None,
    # schedule_interval='0 9 * * *',
    tags=["lambda", "imageprocessing"],
)

# arg = json.dumps(kwargs['dag_run'].conf
# print(arg)
face_detection = BranchPythonOperator(
    depends_on_past=False,
    task_id="face_detection",
    python_callable=face_detection,
    dag=dag,
)

# [START howto_operator_bash]
photo_not_meet_requirement = BashOperator(
    task_id="photo_not_meet_requirement",
    bash_command="echo photo_not_meet_requirement",
    dag=dag,
)
check_duplicate = BranchPythonOperator(
    task_id="check_duplicate",
    python_callable=check_duplicate,
    dag=dag,
)
duplicate_face = BashOperator(
    task_id="duplicate_face",
    bash_command="echo duplicate_face",
    dag=dag,
)
failure = BashOperator(
    task_id="failure",
    bash_command="echo failure",
    dag=dag,
)

parallel_processing = DummyOperator(
    task_id="parallel_processing",
    dag=dag,
)
add_face_index = PythonOperator(
    task_id="add_face_index",
    python_callable=add_face_index,
    dag=dag,
)
create_thumbnail = PythonOperator(
    task_id="create_thumbnail",
    python_callable=create_thumbnail,
    dag=dag,
)
persist_data = PythonOperator(
    task_id="persist_data",
    python_callable=persist_data,
    dag=dag,
)

face_detection >> [photo_not_meet_requirement, check_duplicate, failure]
check_duplicate >> [duplicate_face, failure, parallel_processing]
parallel_processing >> add_face_index >> persist_data
parallel_processing >> create_thumbnail >> persist_data
