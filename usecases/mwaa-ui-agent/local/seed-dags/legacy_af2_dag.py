# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""An Airflow 2 style DAG that no longer imports on Airflow 3.

Shows up under DAG import errors. Ask the agent: "Are there any DAG import errors?"
"""

from airflow import DAG
from airflow.operators.dummy import DummyOperator  # removed in Airflow 3
from airflow.utils.dates import days_ago  # removed in Airflow 3

with DAG(dag_id="legacy_af2_dag", schedule_interval="@daily", start_date=days_ago(1), catchup=False) as dag:
    DummyOperator(task_id="start")
