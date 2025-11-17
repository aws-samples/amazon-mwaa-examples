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
- emr-serverless:StartJobRun - Start EMR Serverless job runs
- emr-serverless:GetJobRun - Get job run status
- emr-serverless:CreateApplication - Create EMR Serverless applications
- emr-serverless:GetApplication - Get application details
- emr-serverless:DeleteApplication - Delete EMR Serverless applications
- s3:GetObject - Read job scripts from S3
- s3:PutObject - Write job outputs to S3
- s3:ListBucket - List S3 bucket contents
- iam:PassRole - Pass execution role to EMR Serverless
"""
import os
from datetime import datetime
from airflow import DAG
from airflow.models.param import Param
from airflow.providers.amazon.aws.operators.emr import (
    EmrServerlessCreateApplicationOperator,
    EmrServerlessStartJobOperator,
    EmrServerlessDeleteApplicationOperator,
    EmrServerlessStopApplicationOperator
)
from airflow.providers.amazon.aws.sensors.emr import (
    EmrServerlessApplicationSensor,
    EmrServerlessJobSensor
)
from airflow.providers.amazon.aws.operators.s3 import S3CreateObjectOperator
from airflow.utils.trigger_rule import TriggerRule

default_args = {
    'owner': 'test',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'retries': 0,
}

dag = DAG(
    'emr_serverless_dag',
    default_args=default_args,
    description='Test EMR Serverless operators',
    schedule=None,
    params={
        'role_arn': Param(
            default='arn:aws:iam::111122223333:role/service-role/MyExecutionRole',
            type='string',
            description='IAM role ARN'
        ),
        'script_bucket': Param( 
            default='amzn-s3-demo-bucket',
            type='string',
            description='S3 bucket of spark script'
        ),
        'script_key': Param( 
            default='scripts/pyspark-sample-job.py',
            type='string',
            description='S3 key of spark script'
        ),     
        'log_url': Param(
            default='s3://amzn-s3-demo-bucket/emr-serverless-logs/',
            type='string',
            description='S3 location to write logs'
        )
    }
)

# Uploads sample script to S3
create_script = S3CreateObjectOperator(
    task_id='create_script',
    s3_bucket='{{ params.script_bucket }}',
    s3_key='{{ params.script_key }}',
    replace=True,
    data='''import sys
from pyspark.sql import SparkSession

def main():
    """
    This PySpark job creates sample data and performs basic transformations
    Based on AWS EMR Serverless samples
    """
    
    # Create Spark session
    spark = SparkSession.builder.appName("EMRServerlessPySparkSample").getOrCreate()
    
    print("Starting EMR Serverless PySpark job...")
    
    # Create sample data
    data = [
        ("Alice", 25, "Engineer"),
        ("Bob", 30, "Manager"), 
        ("Charlie", 35, "Analyst"),
        ("Diana", 28, "Developer"),
        ("Eve", 32, "Designer")
    ]
    
    columns = ["name", "age", "role"]
    
    # Create DataFrame
    df = spark.createDataFrame(data, columns)
    
    print("Original data:")
    df.show()
    
    # Perform transformations
    # Filter employees older than 30
    older_employees = df.filter(df.age > 30)
    print("Employees older than 30:")
    older_employees.show()
    
    # Group by role and count
    role_counts = df.groupBy("role").count()
    print("Count by role:")
    role_counts.show()
    
    # Add a new column for age category
    from pyspark.sql.functions import when
    df_with_category = df.withColumn(
        "age_category",
        when(df.age < 30, "Young")
        .when(df.age < 35, "Mid")
        .otherwise("Senior")
    )
    
    print("Data with age categories:")
    df_with_category.show()
    
    # Calculate statistics
    print("Age statistics:")
    df.describe("age").show()
    
    print("EMR Serverless PySpark job completed successfully!")
    
    spark.stop()

if __name__ == "__main__":
    main()
''',
    dag=dag
)

create_app = EmrServerlessCreateApplicationOperator(
    task_id='create_emr_serverless_app',
    job_type='SPARK',
    release_label='emr-7.2.0',
    config={
        'name': 'workflow-demo',
        'initialCapacity': {
            'DRIVER': {
                'workerCount': 1,
                'workerConfiguration': {
                    'cpu': '2vCPU',
                    'memory': '4GB'
                }
            },
            'EXECUTOR': {
                'workerCount': 2,
                'workerConfiguration': {
                    'cpu': '4vCPU',
                    'memory': '8GB'
                }
            }
        },
        'maximumCapacity': {
            'cpu': '20vCPU',
            'memory': '20GB',
            'disk': '100GB'
        }
    },
    wait_for_completion=False,
    dag=dag
)

wait_app = EmrServerlessApplicationSensor(
    task_id='wait_emr_serverless_app',
    application_id="{{ task_instance.xcom_pull(task_ids='create_emr_serverless_app') }}",
    target_states=['STARTED'],
    dag=dag
)

start_job = EmrServerlessStartJobOperator(
    task_id='start_emr_serverless_job',
    application_id="{{ task_instance.xcom_pull(task_ids='create_emr_serverless_app') }}",
    execution_role_arn='{{ params.role_arn }}',
    job_driver={
        'sparkSubmit': {
            'entryPoint': 's3://{{ params.script_bucket }}/{{ params.script_key }}',
            'sparkSubmitParameters': '--conf spark.executor.cores=2 --conf spark.executor.memory=2g --conf spark.driver.cores=1 --conf spark.driver.memory=2g'
        }
    },
    configuration_overrides={
        'monitoringConfiguration': {
            's3MonitoringConfiguration': {
                'logUri': '{{ params.log_url }}'
            }
        }
    },
    wait_for_completion=False,
    dag=dag
)

wait_job = EmrServerlessJobSensor(
    task_id='wait_emr_serverless_job',
    application_id="{{ task_instance.xcom_pull(task_ids='create_emr_serverless_app') }}",
    job_run_id="{{ task_instance.xcom_pull(task_ids='start_emr_serverless_job') }}",
    target_states=["SUCCESS", "FAILED", "CANCELLED"],
    dag=dag
)

stop_app = EmrServerlessStopApplicationOperator(
    task_id="stop_application",
    application_id="{{ task_instance.xcom_pull(task_ids='create_emr_serverless_app') }}",
    force_stop=True,
    trigger_rule=TriggerRule.ALL_DONE,
    dag=dag
)

delete_app = EmrServerlessDeleteApplicationOperator(
    task_id='delete_emr_serverless_app',
    application_id="{{ task_instance.xcom_pull(task_ids='create_emr_serverless_app') }}",
    trigger_rule=TriggerRule.ALL_SUCCESS,
    dag=dag
)

create_app >> wait_app >> start_job >> wait_job >> stop_app >> delete_app

