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
- lambda:CreateFunction - Create Lambda functions
- lambda:DeleteFunction - Delete Lambda functions (for cleanup)
- lambda:InvokeFunction - Execute Lambda functions
- lambda:GetFunction - Get Lambda function details
- iam:PassRole - Pass execution role to Lambda
"""
import os
import zipfile, io
from datetime import datetime
from airflow import DAG
from airflow.models.param import Param
from airflow.providers.amazon.aws.operators.lambda_function import (
    LambdaCreateFunctionOperator,
    LambdaInvokeFunctionOperator
)
from airflow.providers.amazon.aws.sensors.lambda_function import LambdaFunctionStateSensor
from airflow.utils.trigger_rule import TriggerRule

default_args = {
    'owner': 'test',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'retries': 0,
}

dag = DAG(
    'lambda_dag',
    default_args=default_args,
    description='Test Lambda operators',
    schedule=None,
    params={
        'role_arn': Param(
            default=os.environ.get('ROLE_ARN', 'arn:aws:iam::111122223333:role/service-role/MyExecutionRole'),
            type='string',
            description='IAM role ARN for Lambda operations'
        )
    }
)

# Creates a new Lambda function with inline code
lambda_code = '''import json
import boto3
import time

def lambda_handler(event, context):
    try:
        lambda_client = boto3.client('lambda')
        action = event['action']
        
        if action == 'delete_self':
            lambda_client.delete_function(FunctionName=event['function_name'])
            return {'statusCode': 200}
        
        return {
            'statusCode': 200,
            'body': event['value']
        }
    except Exception as e:
        return {
            'statusCode': 200,
            'body': f"Error: {type(e).__name__}: {e}"
        }'''

zip_buffer = io.BytesIO()
with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
    zip_file.writestr('lambda_function.py', lambda_code)
zip_content = zip_buffer.getvalue()

create_function = LambdaCreateFunctionOperator(
    task_id='create_lambda_function',
    function_name='test-function-{{ ds_nodash }}',
    runtime='python3.12',
    role='{{ params.role_arn }}',
    handler='lambda_function.lambda_handler',
    code={'ZipFile': zip_content},
    dag=dag
)

# Waits for Lambda function to reach Active state before proceeding
wait_active = LambdaFunctionStateSensor(
    task_id='wait_function_active',
    function_name='test-function-{{ ds_nodash }}',
    target_states=['Active'],
    dag=dag
)

# Invokes the Lambda function with specified payload
invoke_function = LambdaInvokeFunctionOperator(
    task_id='invoke_lambda_function',
    function_name='test-function-{{ ds_nodash }}',
    payload='{"action": "echo", "value": "Hello World!" }',
    dag=dag
)

# Invokes Lambda function to delete itself (cleanup operation)
delete_function = LambdaInvokeFunctionOperator(
    task_id='delete_lambda_function',
    function_name='test-function-{{ ds_nodash }}',
    payload='{"action": "delete_self", "function_name": "test-function-{{ ds_nodash }}"}',
    trigger_rule=TriggerRule.ALL_DONE,
    dag=dag
)

create_function >> wait_active >> invoke_function >> delete_function
