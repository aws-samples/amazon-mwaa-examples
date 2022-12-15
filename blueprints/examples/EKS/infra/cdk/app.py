#!/usr/bin/env python3
import os

from aws_cdk import (
    aws_ec2,
    App,
    Environment
)

from stacks.eks_setup import EKSRoleStack
from stacks.mwaa_cdk_backend import VpcStack
from stacks.mwaa_cdk_env import MwaaCdkStackEnv
from stacks.s3 import S3Stack
from stacks.s3_deploy import S3SDeploytack

from stacks.common import constants

default_env = Environment(
    region=os.environ['CDK_DEFAULT_REGION'],
    account=os.environ['CDK_DEFAULT_ACCOUNT']
)

app = App()

vpc: aws_ec2.Vpc = VpcStack(
    scope=app,
    construct_id=f'{constants.ID}-infra-vpc',
    env=default_env,
    cidr=constants.CIDR,
    max_azs=constants.MAZ_AZS,
    cidr_mask=constants.CIDR_MASK
).vpc

b_stack = S3Stack(
    scope=app,
    construct_id=f'{constants.ID}-infra-bucket',
    env=default_env,
    bucket_name=constants.DAGS_S3_LOCATION,
    vpc=vpc
)

mwaa_env = MwaaCdkStackEnv(
    scope=app,
    construct_id=f'{constants.ID}-infra-env',
    env=default_env,
    vpc=vpc
)
mwaa_env.add_dependency(b_stack)

deploy = S3SDeploytack(app, f'{constants.ID}-s3-deploy', env=default_env, bucket=b_stack.bucket)
deploy.add_dependency(b_stack)

# create a role for the EKS nodegroup
eks_nodegroup_role = EKSRoleStack(app, f'{constants.ID}-eks-deps', env=default_env)
eks_nodegroup_role.add_dependency(mwaa_env)

app.synth()
