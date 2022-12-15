import os
from datetime import datetime
from airflow.models.dag import DAG
from airflow.providers.amazon.aws.hooks.eks import ClusterStates, NodegroupStates
from airflow.providers.amazon.aws.operators.eks import (
    EksDeleteClusterOperator,
    EksDeleteNodegroupOperator
)
from airflow.providers.amazon.aws.sensors.eks import EksClusterStateSensor, EksNodegroupStateSensor
import os

CLUSTER_NAME = os.environ.get('AIRFLOW__CDK__CLUSTER_NAME')
NODEGROUP_NAME = os.environ.get('AIRFLOW__CDK__NODEGROUP_NAME')

with DAG(
        dag_id='delete_eks_cluster_nodegroup',
        schedule_interval=None,
        start_date=datetime(2022, 11, 1),
        tags=['eks', 'eks-operator'],
        catchup=False,
) as dag:
    delete_nodegroup = EksDeleteNodegroupOperator(
        task_id='delete_eks_nodegroup',
        cluster_name=CLUSTER_NAME,
        nodegroup_name=NODEGROUP_NAME,
    )

    await_delete_nodegroup = EksNodegroupStateSensor(
        task_id='wait_for_delete_nodegroup',
        cluster_name=CLUSTER_NAME,
        nodegroup_name=NODEGROUP_NAME,
        target_state=NodegroupStates.NONEXISTENT,
    )

    delete_cluster = EksDeleteClusterOperator(
        task_id='delete_eks_cluster',
        cluster_name=CLUSTER_NAME,
    )

    await_delete_cluster = EksClusterStateSensor(
        task_id='wait_for_delete_cluster',
        cluster_name=CLUSTER_NAME,
        target_state=ClusterStates.NONEXISTENT,
    )

    (
            delete_nodegroup
            >> await_delete_nodegroup
            >> delete_cluster
            >> await_delete_cluster
    )
