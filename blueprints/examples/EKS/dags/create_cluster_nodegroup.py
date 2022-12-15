import boto3
import os
from datetime import datetime
from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.amazon.aws.hooks.eks import ClusterStates, NodegroupStates
from airflow.providers.amazon.aws.operators.eks import (
    EksCreateClusterOperator,
    EksCreateNodegroupOperator,
)
from airflow.providers.amazon.aws.sensors.eks import EksClusterStateSensor, EksNodegroupStateSensor
import os

VPC = os.environ.get('AIRFLOW__CDK__VPC_ID')
CLUSTER_NAME = os.environ.get('AIRFLOW__CDK__CLUSTER_NAME')
SUBNETS = os.environ.get('AIRFLOW__CDK__SUBNETS').split(',')
CLUSTER_ROLE = os.environ.get('AIRFLOW__CDK__CLUSTER_ROLE')
NODEGROUP_ROLE = os.environ.get('AIRFLOW__CDK__NODEGROUP_ROLE')
NODEGROUP_NAME = os.environ.get('AIRFLOW__CDK__NODEGROUP_NAME')
MWAA_ENV = os.environ.get('AIRFLOW__CDK__MWAA_ENV')


def create_ingress_rule(eksClusterName, mwaaEnvName, vpcId, **kwargs):
    eks = boto3.client('eks')
    eks_cluster = eks.describe_cluster(
        name=eksClusterName
    )
    eks_security_group_id = eks_cluster['cluster']['resourcesVpcConfig']['clusterSecurityGroupId']

    mwaa = boto3.client('mwaa')
    response = mwaa.get_environment(
        Name=mwaaEnvName
    )
    mwaa_security_group_id = response['Environment']['NetworkConfiguration']['SecurityGroupIds'][0]

    ec2 = boto3.client('ec2')
    ec2.authorize_security_group_ingress(
        GroupId=eks_security_group_id,
        IpPermissions=[
            {'IpProtocol': '-1',
             'UserIdGroupPairs': [{'GroupId': mwaa_security_group_id, 'VpcId': vpcId}]}
        ],
    )


VPC_CONFIG = {
    'subnetIds': SUBNETS,
    'endpointPublicAccess': True,
    'endpointPrivateAccess': True,
}

with DAG(
        dag_id='create_eks_cluster_nodegroup',
        schedule_interval=None,
        start_date=datetime(2022, 11, 1),
        tags=['eks', 'eks-operator'],
        catchup=False,
) as dag:
    create_cluster = EksCreateClusterOperator(
        task_id='create_eks_cluster',
        cluster_name=CLUSTER_NAME,
        cluster_role_arn=CLUSTER_ROLE,
        resources_vpc_config=VPC_CONFIG,
        compute=None,
    )

    await_create_cluster = EksClusterStateSensor(
        task_id='wait_for_create_cluster',
        cluster_name=CLUSTER_NAME,
        target_state=ClusterStates.ACTIVE,
    )

    create_nodegroup = EksCreateNodegroupOperator(
        task_id='create_eks_nodegroup',
        cluster_name=CLUSTER_NAME,
        nodegroup_name=NODEGROUP_NAME,
        nodegroup_subnets=SUBNETS,
        nodegroup_role_arn=NODEGROUP_ROLE,
    )

    await_create_nodegroup = EksNodegroupStateSensor(
        task_id='wait_for_create_nodegroup',
        cluster_name=CLUSTER_NAME,
        nodegroup_name=NODEGROUP_NAME,
        target_state=NodegroupStates.ACTIVE,
    )

    create_sg_ingress = PythonOperator(
        task_id="create_ingress_rule",
        python_callable=create_ingress_rule,
        op_kwargs={
            'eksClusterName': CLUSTER_NAME,
            'mwaaEnvName': MWAA_ENV,
            'vpcId': VPC
        },
        provide_context=True
    )

    (
            create_cluster
            >> await_create_cluster
            >> create_nodegroup
            >> await_create_nodegroup
            >> create_sg_ingress
    )
