# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

#!/usr/bin/env python3

import aws_cdk as cdk
from stacks.EKSStack import EmrEksCdkStack
import os

default_env = cdk.Environment(
    region=os.environ['CDK_DEFAULT_REGION'],
    account=os.environ['CDK_DEFAULT_ACCOUNT']
)


config = {
}

app = cdk.App()
eks = EmrEksCdkStack(app, "emr-eks-cdk", env=default_env, props=config)

app.synth()
