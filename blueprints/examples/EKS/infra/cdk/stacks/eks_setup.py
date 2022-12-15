from aws_cdk import (
    Stack,
    aws_iam,
    aws_ssm,
    CfnOutput
)
from constructs import Construct

from .iam import pass_role_policy
from .common import constants


class EKSRoleStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # get the mwaa role from SSM. This role needs pass role to the NodeGroup role
        mwaa_role_name = aws_ssm.StringParameter.value_for_string_parameter(
            self, parameter_name=f'/{constants.ID}/mwaa-role'
        )

        eks_role = nodegroup_iam_role_and_passrole_policy(
            self,
            aws_iam.Role.from_role_arn(self, 'eks_role_arn', mwaa_role_name))

        # store the EKS role as SSM Parameter
        aws_ssm.StringParameter(
            self,
            'ssm-eks-role',
            parameter_name=f'/{constants.ID}/eks-role',
            description='EKS Nodegroup Role ARN',
            string_value=eks_role.role_arn
        )
        CfnOutput(self, "NODE_GROUP_ROLE_ARN", value=eks_role.role_arn)


def nodegroup_iam_role_and_passrole_policy(scope: Construct, runner_role: aws_iam.IRole) -> aws_iam.Role:
    r = aws_iam.Role(
        scope,
        "mwaa-pod-role",
        assumed_by=aws_iam.CompositePrincipal(
            aws_iam.ServicePrincipal("airflow.amazonaws.com"),
            aws_iam.ServicePrincipal("airflow-env.amazonaws.com"),
            aws_iam.ServicePrincipal("ec2.amazonaws.com"),
            aws_iam.ServicePrincipal("eks.amazonaws.com"),
            aws_iam.ServicePrincipal("eks-fargate-pods.amazonaws.com"),
            aws_iam.ServicePrincipal("eks-nodegroup.amazonaws.com"),
        ),
    )

    runner_role.add_to_principal_policy(pass_role_policy([r.role_arn]))

    for p in [
        'AmazonEKSClusterPolicy',
        'AmazonEKSWorkerNodePolicy',
        'AmazonEC2ContainerRegistryReadOnly',
        'AmazonEKS_CNI_Policy'
    ]:
        r.add_managed_policy(aws_iam.ManagedPolicy.from_aws_managed_policy_name(p))

    return r
