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
import logging

from airflow import DAG

from airflow.operators.python import PythonOperator
from airflow.providers.amazon.aws.operators.glue_crawler import GlueCrawlerOperator
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator

from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor

DAG_ID = os.path.basename(__file__).replace(".py", "")
SOURCE_BUCKET_NAME = '{{ dag_run.conf.get("source_bucket_name") }}'
TARGET_BUCKET_NAME = '{{ dag_run.conf.get("target_bucket_name") }}'
GLUE_DB_NAME = '{{ dag_run.conf.get("glue_db_name") }}'
GLUE_ROLE_ARN = '{{ dag_run.conf.get("glue_role_arn") }}'
GLUE_ROLE_NAME = '{{ dag_run.conf.get("glue_role_name") }}'

with DAG(
    dag_id=DAG_ID,    
    schedule=None,
    start_date=pendulum.datetime(2023, 1, 1, tz="UTC"),
    catchup=False,
    tags=["aws-demo", "standard-operators", "S3", "Glue"],
) as dag:

    wait_for_source_data = S3KeySensor(
        task_id="WaitForSourceData",
        bucket_name=SOURCE_BUCKET_NAME,
        bucket_key=["persons.json", "memberships.json", "organizations.json"],
        aws_conn_id="aws_default"
    )

    glue_crawler_config = {
        "Name": "glue_crawler_legislators",
        "Role": GLUE_ROLE_ARN,
        "DatabaseName": GLUE_DB_NAME,
        "Targets": {"S3Targets": [{"Path": f"{SOURCE_BUCKET_NAME}"}]},
    }

    crawl_source_data = GlueCrawlerOperator(
        task_id="CrawlSourceData",
        config=glue_crawler_config,
        aws_conn_id="aws_default"
    )

    process_source_data = GlueJobOperator(
        task_id="ProcessSourceData",
        job_name="join-relationalize-legislators",
        script_location=f"s3://{SOURCE_BUCKET_NAME}/glue-script-join-relationalize.py",
        s3_bucket=SOURCE_BUCKET_NAME,
        iam_role_name=GLUE_ROLE_NAME,
        create_job_kwargs={"GlueVersion": "4.0", "NumberOfWorkers": 2, "WorkerType": "G.1X"},
        aws_conn_id="aws_default",
        script_args={
            "--db_name": GLUE_DB_NAME,
            "--target_bucket_name": TARGET_BUCKET_NAME
        }
    )

    wait_for_source_data >> crawl_source_data >> process_source_data