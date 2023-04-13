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

import os
from airflow import DAG, Dataset
from airflow.decorators import dag, task
import pendulum
from airflow.operators.python import PythonOperator

weather_dataset = Dataset("s3://YOUR_OWN_S3_BUCKET/data/test.csv")

S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "YOUR_OWN_S3_BUCKET")
S3_BUCKET_PREFIX = os.getenv("S3_BUCKET_PREFIX", "data")

@dag(
    dag_id="data_aware_consumer",
    description="This dag demonstrates a simple dataset consumer",
    start_date=pendulum.datetime(2023, 1, 1, tz="UTC"),
    schedule=[weather_dataset],
    tags=["airflow2.4", "dataset", "dataset-consumer"])
def data_aware_consumer():
   
    @task(task_id="list_objects")
    def _list_objects(bucket, prefix):
        import boto3
        import logging
        
        ## Read data from the S3 bucket and write it to the logs
        s3_client = boto3.client("s3")
        response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
        files = response.get("Contents")
        for file in files:
            logging.info(f"file_name: {file['Key']}, size: {file['Size']}")

    _list_objects(S3_BUCKET_NAME, S3_BUCKET_PREFIX) 

## Run the DAG
data_aware_consumer()