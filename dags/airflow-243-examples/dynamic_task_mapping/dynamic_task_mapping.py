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

from airflow import DAG, XComArg
from airflow.decorators import dag, task
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.providers.amazon.aws.operators.s3 import S3ListOperator

S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "YOUR_OWN_S3_BUCKET")
S3_BUCKET_PREFIX = os.getenv("S3_BUCKET_PREFIX", "data")

@dag(
    dag_id="dynamic_task_mapping", 
    description="This dag demonstrates a dynamic task mapping",
    schedule=None,
    start_date=pendulum.datetime(2023, 1, 1, tz="UTC"),)
def dynamic_task_mapping():

    files = S3ListOperator(
        task_id="dynamic_task_mapping_get_input",
        bucket=S3_BUCKET_NAME,
        prefix=S3_BUCKET_PREFIX,
    )

    ## Count lines in a single file
    @task
    def count_lines(aws_conn_id, bucket, file):
        hook = S3Hook(aws_conn_id=aws_conn_id)

        return len(hook.read_key(file, bucket).splitlines())

    ## Count total lines across files
    @task
    def total(lines):
        return sum(lines)

    counts = count_lines.partial(aws_conn_id="aws_default", bucket=files.bucket).expand(
        file=XComArg(files)
    )
    total(lines=counts)

## Run the DAG
dynamic_task_mapping()