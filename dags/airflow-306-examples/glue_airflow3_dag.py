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
- glue:StartJobRun - Start Glue job executions
- glue:GetJobRun - Get Glue job run status
- glue:CreateJob - Create Glue jobs
- iam:PassRole - Pass execution role to Glue
- s3:GetObject - Read Glue scripts from S3
- s3:PutObject - Write objects to S3 buckets
"""
import os
from datetime import datetime
from airflow import DAG
from airflow.models.param import Param
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
from airflow.providers.amazon.aws.sensors.glue import GlueJobSensor
from airflow.providers.amazon.aws.operators.s3 import S3CreateObjectOperator

default_args = {
    'owner': 'test',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'retries': 0,
}

dag = DAG(
    'glue_dag',
    default_args=default_args,
    description='Test Glue operators',
    schedule=None,
    params={
        'role_name': Param(
            default='MyExecutionRole',
            type='string',
            description='IAM role name'
        ),
        'script_bucket': Param( 
            default='amzn-s3-demo-bucket',
            type='string',
            description='S3 bucket of spark script'
        ),
        'script_key': Param( 
            default='scripts/glue-sample-job.py',
            type='string',
            description='S3 key of spark script'
        ),        
    }    
)

# Use a consistent job name variable
job_name = 'glue5-python3-job-{{ ds_nodash }}'

# Uploads sample script to S3
create_script = S3CreateObjectOperator(
    task_id='create_script',
    s3_bucket='{{ params.script_bucket }}',
    s3_key='{{ params.script_key }}',
    replace=True,
    data='''#!/usr/bin/env python3

import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql import SparkSession

# Initialize Glue job
args = getResolvedOptions(sys.argv, ['JOB_NAME'])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

print("=== Glue 5.0 Job Started ===")
print(f"Python version: {sys.version}")
print(f"Spark version: {spark.version}")
print(f"Job name: {args['JOB_NAME']}")

# Create test DataFrame
data = [("test", 1, "success"), ("glue", 2, "running"), ("job", 3, "complete")]
columns = ["name", "id", "status"]
df = spark.createDataFrame(data, columns)

print("Created test DataFrame:")
df.show()

print("=== Glue 5.0 Job Completed Successfully ===")
job.commit()
''',
    dag=dag
)

# Starts a Glue ETL job with specified script and configuration
run_glue_job = GlueJobOperator(
    task_id='run_glue_job',
    job_name=job_name,
    iam_role_name='{{ params.role_name }}',
    create_job_kwargs={
        'GlueVersion': '5.0',
        'Command': {
            'Name': 'glueetl',
            'ScriptLocation': 's3://{{ params.script_bucket }}/{{ params.script_key }}',
            'PythonVersion': '3'
        },
        'DefaultArguments': {
            '--job-language': 'python',
            '--enable-metrics': '',
            '--enable-continuous-cloudwatch-log': 'true'
        },
        'MaxRetries': 0,
        'Timeout': 60
    },
    wait_for_completion=False,
    dag=dag
)

# Waits for the Glue job to complete successfully
wait_glue_job = GlueJobSensor(
    task_id='wait_glue_job',
    job_name=job_name,
    run_id="{{ task_instance.xcom_pull(task_ids='run_glue_job') }}",
    dag=dag
)

create_script >> run_glue_job >> wait_glue_job
