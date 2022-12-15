from datetime import datetime
from airflow.models.dag import DAG
from airflow.providers.amazon.aws.operators.eks import EksPodOperator

import os

CLUSTER_NAME = os.environ.get('AIRFLOW__CDK__CLUSTER_NAME')

with DAG(
        dag_id='eks_run_pod',
        schedule_interval=None,
        start_date=datetime(2022, 11, 1),
        tags=['eks', 'eks-operator'],
        catchup=False,

) as dag:
    run_pod = EksPodOperator(
        task_id="run_pod",
        cluster_name=CLUSTER_NAME,
        pod_name="run_pod",
        image="amazon/aws-cli:latest",
        cmds=["sh", "-c", "ls"],
        labels={"demo": "EksPodOperator"},
        get_logs=True,
        region=os.environ['AWS_DEFAULT_REGION'],
        is_delete_operator_pod=True,
    )

    (
        run_pod
    )
