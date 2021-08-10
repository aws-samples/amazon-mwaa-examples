#!/usr/bin/env python3
import os

from aws_cdk import core as cdk
from aws_cdk import core

from infra.vpc_stack import VpcStack
from infra.codeartifact_stack import CodeArtifactStack
from infra.lambda_cron_stack import LambdaCronStack
from infra.s3_stack import S3Stack
from infra.mwaa_stack import MwaaStack


app = core.App()
env = core.Environment(region=os.environ.get("AWS_REGION"))

vpc = VpcStack(app, "VpcStack", env=env)
ca = CodeArtifactStack(app, "CodeArtifactStack", env=env)
s3 = S3Stack(app, "S3Stack", env=env)
lambda_cron = LambdaCronStack(app, "LambdaCronStack", ca, s3, env=env)
mwaa = MwaaStack(app, "MwaaStack", vpc, s3, env=env)
mwaa.add_dependency(lambda_cron)

app.synth()
