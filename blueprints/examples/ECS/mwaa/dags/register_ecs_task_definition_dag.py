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
from airflow.providers.amazon.aws.operators.ecs import EcsRegisterTaskDefinitionOperator
from airflow.utils.dates import days_ago

# Read ECR image URI from SSM
SSM_CLIENT = boto3.client('ssm')
SPARK_IMAGE = str(SSM_CLIENT.get_parameter(Name='/ecs/mwaa/spark-image', \
    WithDecryption=True)['Parameter']['Value'])

# Read ECS task from SSM
ECS_TASK_ROLE_ARN = str(SSM_CLIENT.get_parameter(Name='/ecs/mwaa/task-role', \
    WithDecryption=True)['Parameter']['Value'])

# GET Family Name from SSM
FAMILY_NAME = str(SSM_CLIENT.get_parameter(Name='/ecs/mwaa/stack-name', \
    WithDecryption=True)['Parameter']['Value'])

# DAG for Registering ECS Task definition
with DAG(dag_id="register_ecs_task_definition_dag", \
    schedule_interval=None, catchup=False, \
    start_date=days_ago(1)) as dag:
    # Create ECS Task Definition
    # https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_TaskDefinition.html
    REGISTER_SPARK_TASK = EcsRegisterTaskDefinitionOperator(
        task_id="REGISTER_SPARK_TASK",
        family=FAMILY_NAME,
        container_definitions=[
            {
                "name": "spark-processing-image",
                "image": SPARK_IMAGE
            }
        ],
        register_task_kwargs={
            "cpu": "256",
            "memory": "512",
            "networkMode": "awsvpc",
            "executionRoleArn": ECS_TASK_ROLE_ARN,
            "requiresCompatibilities": ["FARGATE"]
        },
        wait_for_completion=True
    )
    print(REGISTER_SPARK_TASK.output)
