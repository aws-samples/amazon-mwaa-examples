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
import os
import boto3
from airflow import DAG
from airflow.providers.amazon.aws.operators.ecs import EcsDeleteClusterOperator
from airflow.utils.dates import days_ago

# Cluster Name
CLUSTER_NAME = os.environ.get('AIRFLOW__CDK__CLUSTER_NAME')

# DELETE ECS Cluster
with DAG(dag_id="delete_ecs_cluster_dag", schedule_interval=None, \
    catchup=False, start_date=days_ago(1)) as dag:
    # Airflow Task
    DELETE_CLUSTER_TASK = EcsDeleteClusterOperator(task_id="DELETE_CLUSTER_TASK", \
        cluster_name=CLUSTER_NAME, wait_for_completion=True)
