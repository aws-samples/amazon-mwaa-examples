"""
-*- coding: utf-8 -*-
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is furnished to do so.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
# FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
# COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
# IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""
import boto3
from airflow import DAG
from airflow.providers.amazon.aws.operators.ecs import EcsDeregisterTaskDefinitionOperator
from airflow.utils.dates import days_ago

# Read task name from SSM
SSM_CLIENT = boto3.client('ssm')
TASK_NAME = str(SSM_CLIENT.get_parameter(Name='/ecs/mwaa/stack-name', \
    WithDecryption=True)['Parameter']['Value'])+":1"

# Get Latest Task definition
ECS_CLIENT = boto3.client('ecs')
TASK_DEFINITION = ':'.join(
    ECS_CLIENT.describe_task_definition(
        taskDefinition=TASK_NAME
    )['taskDefinition']['taskDefinitionArn'].split(':')[-2:]).split('/')[-1]

# Deregister ECS Task Definition
with DAG(dag_id="deregister_ecs_task_definition_dag", schedule_interval=None, \
    catchup=False, start_date=days_ago(1)) as dag:
    # Airflow Task
    DEREGISTER_TASK_DEFINITION = EcsDeregisterTaskDefinitionOperator(task_id="DEREGISTER_TASK_DEFINITION", \
        task_definition=TASK_DEFINITION, wait_for_completion=True)
