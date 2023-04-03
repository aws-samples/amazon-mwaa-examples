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
from airflow.providers.amazon.aws.operators.ecs import EcsRunTaskOperator
from airflow.utils.dates import days_ago

# Read paramters
ECS_PRIVATE_SUBNETS = os.environ.get('AIRFLOW__CDK__SUBNET_ID')
CLUSTER_NAME = os.environ.get('AIRFLOW__CDK__CLUSTER_NAME')
TASK_DEFINITION = os.environ.get('AIRFLOW__CDK__STACK_NAME')
LOG_GROUP = "/aws/mwaaa/blueprint"
LOG_PREFIX = "spark"
ECS_SECURITY_GROUP = str(SSM_CLIENT.get_parameter(Name='/ecs/mwaa/security-group', \
    WithDecryption=True)['Parameter']['Value'])

# Run Spark Processing task
with DAG(dag_id="run_ecs_task_dag", schedule_interval=None, \
    catchup=False, start_date=days_ago(1)) as dag:
    SPARK_PROCESSING_TASK = EcsRunTaskOperator(
        task_id="SPARK_PROCESSING_TASK",
        task_definition=TASK_DEFINITION,
        cluster=CLUSTER_NAME,
        launch_type='FARGATE',
        aws_conn_id="aws_ecs",
        network_configuration={
            "awsvpcConfiguration": {
                "securityGroups": [ECS_SECURITY_GROUP],
                "subnets": list(ECS_PRIVATE_SUBNETS.split(",")),
            },
        },
        overrides={
            "containerOverrides": [
            ],
        },
        awslogs_group=LOG_GROUP,
        awslogs_stream_prefix=LOG_PREFIX,
        wait_for_completion=True)
