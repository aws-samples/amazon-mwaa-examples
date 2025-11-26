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

Required IAM Permissions:
- s3:CreateBucket - Create S3 buckets
- s3:DeleteBucket - Delete S3 buckets  
- s3:ListBucket - List objects in S3 buckets
- s3:GetObject - Read objects from S3 buckets
- s3:PutObject - Write objects to S3 buckets
- s3:DeleteObject - Delete objects from S3 buckets
"""
from datetime import datetime
from airflow import DAG
from airflow.providers.amazon.aws.operators.s3 import (
    S3CreateBucketOperator,
    S3CreateObjectOperator,
    S3ListOperator,
    S3DeleteBucketOperator,
    S3DeleteObjectsOperator
)
from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor

default_args = {
    'owner': 'test',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'retries': 0,
}

dag = DAG(
    's3_dag',
    default_args=default_args,
    description='Test S3 operators',
    schedule=None,
)

# Creates a new S3 bucket with the specified name
create_bucket = S3CreateBucketOperator(
    task_id='create_test_bucket',
    bucket_name='test-bucket-{{ ds_nodash }}',
    dag=dag
)

# Creates a text object in the S3 bucket with specified content
create_object = S3CreateObjectOperator(
    task_id='create_test_object',
    s3_bucket='test-bucket-{{ ds_nodash }}',
    s3_key='test-file.txt',
    data='Hello World',
    dag=dag
)

# Lists all objects in the specified S3 bucket
list_objects = S3ListOperator(
    task_id='list_objects',
    bucket='test-bucket-{{ ds_nodash }}',
    dag=dag
)

# Waits for a specific key/object to exist in the S3 bucket before proceeding
wait_for_key = S3KeySensor(
    task_id='wait_for_key',
    bucket_name='test-bucket-{{ ds_nodash }}',
    bucket_key='test-file.txt',
    dag=dag
)

# Deletes specified objects from the S3 bucket
delete_objects = S3DeleteObjectsOperator(
    task_id='delete_objects',
    bucket='test-bucket-{{ ds_nodash }}',
    keys=['test-file.txt'],
    dag=dag
)

# Deletes the S3 bucket (bucket must be empty)
delete_bucket = S3DeleteBucketOperator(
    task_id='delete_test_bucket',
    bucket_name='test-bucket-{{ ds_nodash }}',
    dag=dag
)

create_bucket >> create_object >> wait_for_key >> list_objects >> delete_objects >> delete_bucket
