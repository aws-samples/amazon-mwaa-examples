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
import pendulum

from airflow import DAG, Dataset
from airflow.decorators import dag, task
from airflow.decorators import task
from airflow.operators.python import PythonOperator

weather_dataset = Dataset("s3://YOUR_OWN_S3_BUCKET/data/test.csv")

S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "YOUR_OWN_S3_BUCKET")
S3_BUCKET_PREFIX = os.getenv("S3_BUCKET_PREFIX", "data")

@dag(
    dag_id='data_aware_producer',
    description="This dag demonstrates a simple dataset producer",
    schedule=None,
    start_date=pendulum.datetime(2023, 1, 1, tz="UTC"),
    catchup=False,
    tags=["airflow2.4", "dataset", "dataset-producer"],
)
def data_aware_producer():
    
    @task(task_id="transfer_api_to_s3", outlets=[weather_dataset])
    def _transfer_from_api_to_s3(bucket, key):
        import requests
        import logging
        import pandas as pd

        import boto3
        from botocore.exceptions import ClientError
        from tempfile import NamedTemporaryFile

        url = "https://www.7timer.info/bin/astro.php?lon=113.2&lat=23.1&ac=0&unit=metric&output=json&tzshift=0"

        ## Pull data from a random public API ##
        try:
            logging.info("Attempting to get data from api")
            response = requests.get(url)
            logging.info("Response: %s", response.json())
            response.raise_for_status()
        except Exception as ex:
            logging.error(
                "Exception occured while trying to get response from API")
            logging.error(ex)

        data = response.json()

        ## Convert the data into a dataframe
        df = pd.DataFrame.from_records(data)

        ## Upload the data to S3 as a CSV file
        with NamedTemporaryFile("w+b") as file:
            df.to_csv(file.name, index=False)
            s3_client = boto3.client('s3')
            try:
                response = s3_client.upload_file(file.name, bucket, key)
            except ClientError as e:
                logging.error(e)
                return False
            logging.info("Storing object: %s/%s.", bucket, key)
            return True

    _transfer_from_api_to_s3(S3_BUCKET_NAME, f"{S3_BUCKET_PREFIX}/test.csv")

## Run the DAG
data_aware_producer()
