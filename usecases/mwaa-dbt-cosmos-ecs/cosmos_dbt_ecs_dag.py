"""
Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

Self-contained Cosmos dbt DAG with AWS ECS execution on Airflow 3.0.6 / MWAA.

Provisions all infrastructure, builds a dbt-duckdb Docker image, seeds data
to S3, then runs dbt models via Cosmos DbtTaskGroup on ECS Fargate. Each model
reads/writes Parquet on S3 so containers don't need shared state.

Flow:
  1. CloudFormation: ECR, CodeBuild, ECS cluster, task def, IAM roles
  2. CodeBuild: build dbt-duckdb Docker image → ECR
  3. ECS task: dbt seed + export seed CSVs to S3 as Parquet
  4. Cosmos DbtTaskGroup: run each model as separate ECS task (S3 ↔ S3)
  5. CloudFormation: delete stack (always)
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.amazon.aws.operators.cloud_formation import (
    CloudFormationCreateStackOperator,
    CloudFormationDeleteStackOperator,
)
from airflow.providers.amazon.aws.operators.ecs import EcsRunTaskOperator
from airflow.providers.amazon.aws.sensors.cloud_formation import (
    CloudFormationCreateStackSensor,
)

from cosmos import (
    DbtTaskGroup,
    ExecutionConfig,
    ExecutionMode,
    LoadMode,
    ProfileConfig,
    ProjectConfig,
    RenderConfig,
)
from cosmos.constants import TestBehavior

# ---------------------------------------------------------------------------
# Configuration — derived from MWAA environment variables
# ---------------------------------------------------------------------------
import os
import re
import boto3

# Parse region + account from MWAA__LOGGING__AIRFLOW_TASK_LOG_GROUP_ARN
# Format: arn:aws:logs:<region>:<account>:log-group:airflow-<env_name>-Task
_log_arn = os.environ.get("MWAA__LOGGING__AIRFLOW_TASK_LOG_GROUP_ARN", "")
_arn_parts = _log_arn.split(":")
AWS_REGION = _arn_parts[3] if len(_arn_parts) > 5 else os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
ACCOUNT_ID = _arn_parts[4] if len(_arn_parts) > 5 else "unknown"
_env_name = re.sub(r"^airflow-(.+)-Task$", r"\1", _arn_parts[-1]) if len(_arn_parts) > 5 else ""

# Fetch VPC config and S3 bucket from the MWAA environment
_mwaa = boto3.client("mwaa", region_name=AWS_REGION)
_env = _mwaa.get_environment(Name=_env_name)["Environment"]
_net = _env["NetworkConfiguration"]
S3_BUCKET = _env["SourceBucketArn"].split(":::")[-1]
_MWAA_SUBNETS = _net["SubnetIds"]
_MWAA_SG = _net["SecurityGroupIds"][0]

# Look up public subnets in the same VPC for ECS Fargate (need internet access)
_ec2 = boto3.client("ec2", region_name=AWS_REGION)
_vpc_id = _ec2.describe_subnets(SubnetIds=[_MWAA_SUBNETS[0]])["Subnets"][0]["VpcId"]
_all_subnets = _ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [_vpc_id]}])["Subnets"]
_public_subnets = [s["SubnetId"] for s in _all_subnets if s["MapPublicIpOnLaunch"]]
ECS_SUBNETS = _public_subnets if _public_subnets else _MWAA_SUBNETS
SECURITY_GROUP = _MWAA_SG

# Static names for provisioned resources
STACK_NAME = "cosmos-dbt-ecs-selfcontained"
ECR_REPO_NAME = "cosmos-dbt-duckdb"
ECS_CLUSTER_NAME = "cosmos-dbt-cluster"
TASK_DEF_FAMILY = "cosmos-dbt-task"
CONTAINER_NAME = "dbt"
CODEBUILD_PROJECT = "cosmos-dbt-image-build"
S3_OUTPUT_PREFIX = "dbt_output"

ECR_IMAGE_URI = f"{ACCOUNT_ID}.dkr.ecr.{AWS_REGION}.amazonaws.com/{ECR_REPO_NAME}:latest"
DBT_PROJECT_PATH = Path(__file__).parent / "dbt_project"

# ---------------------------------------------------------------------------
# CloudFormation template
# ---------------------------------------------------------------------------
CFN_TEMPLATE = json.dumps({
    "AWSTemplateFormatVersion": "2010-09-09",
    "Description": "Self-contained ECS + CodeBuild for Cosmos dbt",
    "Resources": {
        "ECRRepo": {
            "Type": "AWS::ECR::Repository",
            "Properties": {
                "RepositoryName": ECR_REPO_NAME,
                "ImageScanningConfiguration": {"ScanOnPush": False},
                "EmptyOnDelete": True,
            },
        },
        "CodeBuildRole": {
            "Type": "AWS::IAM::Role",
            "Properties": {
                "RoleName": f"{STACK_NAME}-cb-role",
                "AssumeRolePolicyDocument": {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "codebuild.amazonaws.com"}, "Action": "sts:AssumeRole"}]},
                "Policies": [{"PolicyName": "cb", "PolicyDocument": {"Version": "2012-10-17", "Statement": [
                    {"Effect": "Allow", "Action": ["ecr:*"], "Resource": "*"},
                    {"Effect": "Allow", "Action": ["logs:*"], "Resource": "*"},
                    {"Effect": "Allow", "Action": ["s3:GetObject", "s3:GetBucketLocation", "s3:ListBucket"], "Resource": [f"arn:aws:s3:::{S3_BUCKET}", f"arn:aws:s3:::{S3_BUCKET}/*"]},
                ]}}],
            },
        },
        "CodeBuildProject": {
            "Type": "AWS::CodeBuild::Project",
            "DependsOn": ["CodeBuildRole", "ECRRepo"],
            "Properties": {
                "Name": CODEBUILD_PROJECT,
                "ServiceRole": {"Fn::GetAtt": ["CodeBuildRole", "Arn"]},
                "Artifacts": {"Type": "NO_ARTIFACTS"},
                "Environment": {"Type": "LINUX_CONTAINER", "ComputeType": "BUILD_GENERAL1_SMALL", "Image": "aws/codebuild/standard:7.0", "PrivilegedMode": True},
                "Source": {"Type": "NO_SOURCE", "BuildSpec": json.dumps({"version": 0.2, "phases": {
                    "pre_build": {"commands": [f"aws ecr get-login-password --region {AWS_REGION} | docker login --username AWS --password-stdin {ACCOUNT_ID}.dkr.ecr.{AWS_REGION}.amazonaws.com"]},
                    "build": {"commands": [
                        f"aws s3 cp s3://{S3_BUCKET}/dags/3.0/dbt/dbt_project/ ./dbt_project/ --recursive",
                        f"printf 'FROM public.ecr.aws/docker/library/python:3.11-slim\\nRUN pip install --no-cache-dir dbt-duckdb==1.9.1\\nWORKDIR /dbt\\nCOPY dbt_project/ /dbt/\\nCOPY dbt_project/entrypoint.sh /entrypoint.sh\\nRUN chmod +x /entrypoint.sh\\nENTRYPOINT [\"/entrypoint.sh\"]\\n' > Dockerfile",
                        f"docker build -t {ECR_IMAGE_URI} .",
                        f"docker push {ECR_IMAGE_URI}",
                    ]},
                }})},
                "TimeoutInMinutes": 15,
            },
        },
        "ECSTaskExecRole": {
            "Type": "AWS::IAM::Role",
            "Properties": {
                "RoleName": f"{STACK_NAME}-ecs-exec",
                "AssumeRolePolicyDocument": {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "ecs-tasks.amazonaws.com"}, "Action": "sts:AssumeRole"}]},
                "ManagedPolicyArns": ["arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"],
            },
        },
        "ECSTaskRole": {
            "Type": "AWS::IAM::Role",
            "Properties": {
                "RoleName": f"{STACK_NAME}-ecs-task",
                "AssumeRolePolicyDocument": {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "ecs-tasks.amazonaws.com"}, "Action": "sts:AssumeRole"}]},
                "Policies": [{"PolicyName": "task", "PolicyDocument": {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": ["s3:*", "logs:*"], "Resource": "*"}]}}],
            },
        },
        "ECSCluster": {"Type": "AWS::ECS::Cluster", "Properties": {"ClusterName": ECS_CLUSTER_NAME}},
        "LogGroup": {"Type": "AWS::Logs::LogGroup", "Properties": {"LogGroupName": f"/ecs/{TASK_DEF_FAMILY}", "RetentionInDays": 7}},
        "TaskDefinition": {
            "Type": "AWS::ECS::TaskDefinition",
            "DependsOn": ["LogGroup", "ECSTaskExecRole", "ECSTaskRole"],
            "Properties": {
                "Family": TASK_DEF_FAMILY, "NetworkMode": "awsvpc", "RequiresCompatibilities": ["FARGATE"],
                "Cpu": "512", "Memory": "1024",
                "ExecutionRoleArn": {"Fn::GetAtt": ["ECSTaskExecRole", "Arn"]},
                "TaskRoleArn": {"Fn::GetAtt": ["ECSTaskRole", "Arn"]},
                "ContainerDefinitions": [{"Name": CONTAINER_NAME, "Image": ECR_IMAGE_URI, "Essential": True,
                    "LogConfiguration": {"LogDriver": "awslogs", "Options": {"awslogs-group": f"/ecs/{TASK_DEF_FAMILY}", "awslogs-region": AWS_REGION, "awslogs-stream-prefix": "ecs"}}}],
            },
        },
    },
})

NETWORK_CONFIG = {"awsvpcConfiguration": {"subnets": ECS_SUBNETS, "securityGroups": [SECURITY_GROUP], "assignPublicIp": "ENABLED"}}


def ensure_stack_deleted(**context):
    import boto3
    cfn = boto3.client("cloudformation", region_name=AWS_REGION)
    try:
        cfn.describe_stacks(StackName=STACK_NAME)
        print(f"Deleting existing stack {STACK_NAME}...")
        cfn.delete_stack(StackName=STACK_NAME)
        cfn.get_waiter("stack_delete_complete").wait(StackName=STACK_NAME, WaiterConfig={"Delay": 10, "MaxAttempts": 60})
    except cfn.exceptions.ClientError:
        print("No existing stack.")


def build_and_push_image(**context):
    import boto3
    cb = boto3.client("codebuild", region_name=AWS_REGION)
    build_id = cb.start_build(projectName=CODEBUILD_PROJECT)["build"]["id"]
    print(f"Started CodeBuild: {build_id}")
    while True:
        status = cb.batch_get_builds(ids=[build_id])["builds"][0]["buildStatus"]
        print(f"CodeBuild: {status}")
        if status in ("SUCCEEDED", "FAILED", "FAULT", "TIMED_OUT", "STOPPED"):
            break
        time.sleep(15)
    if status != "SUCCEEDED":
        raise RuntimeError(f"CodeBuild failed: {status}")


# ---------------------------------------------------------------------------
# DAG
# ---------------------------------------------------------------------------
with DAG(
    dag_id="cosmos_dbt_ecs_dag",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    tags=["dbt", "cosmos", "ecs", "self-contained"],
    doc_md=__doc__,
) as dag:

    cleanup_old = PythonOperator(task_id="ensure_clean_state", python_callable=ensure_stack_deleted)

    create_stack = CloudFormationCreateStackOperator(
        task_id="create_infra_stack", stack_name=STACK_NAME,
        cloudformation_parameters={"StackName": STACK_NAME, "TemplateBody": CFN_TEMPLATE, "Capabilities": ["CAPABILITY_NAMED_IAM"]},
    )

    wait_stack = CloudFormationCreateStackSensor(task_id="wait_for_infra", stack_name=STACK_NAME, poke_interval=15, timeout=600, retries=3, retry_delay=30)

    build_image = PythonOperator(task_id="build_docker_image", python_callable=build_and_push_image, retries=2, retry_delay=30)

    # Seed data: run dbt seed then export seed tables to S3 as Parquet
    seed_data = EcsRunTaskOperator(
        task_id="dbt_seed_to_s3", retries=2, retry_delay=30,
        cluster=ECS_CLUSTER_NAME, task_definition=TASK_DEF_FAMILY, container_name=CONTAINER_NAME,
        launch_type="FARGATE", network_configuration=NETWORK_CONFIG,
        overrides={"containerOverrides": [{"name": CONTAINER_NAME, "command": ["sh", "-c",
            "dbt seed --project-dir /dbt --profiles-dir /dbt"
            " && dbt run-operation export_seeds_to_s3 --project-dir /dbt --profiles-dir /dbt"
        ], "environment": [
            {"name": "DBT_S3_BUCKET", "value": S3_BUCKET},
            {"name": "AWS_DEFAULT_REGION", "value": AWS_REGION},
        ]}]},
        awslogs_group=f"/ecs/{TASK_DEF_FAMILY}", awslogs_region=AWS_REGION, awslogs_stream_prefix="ecs",
    )

    # Cosmos DbtTaskGroup: each model runs as a separate ECS Fargate task
    # Models read upstream data from S3 Parquet (not local DuckDB refs)
    dbt_models = DbtTaskGroup(
        group_id="dbt_ecs",
        project_config=ProjectConfig(dbt_project_path=str(DBT_PROJECT_PATH)),
        profile_config=ProfileConfig(
            profile_name="sample_dbt_project", target_name="dev",
            profiles_yml_filepath=str(DBT_PROJECT_PATH / "profiles.yml"),
        ),
        execution_config=ExecutionConfig(execution_mode=ExecutionMode.AWS_ECS),
        render_config=RenderConfig(
            load_method=LoadMode.CUSTOM,
            emit_datasets=False,
            test_behavior=TestBehavior.NONE,
            select=["stg_customers", "stg_orders", "customer_orders"],
        ),
        operator_args={
            "project_dir": "/dbt",
            "cluster": ECS_CLUSTER_NAME,
            "task_definition": TASK_DEF_FAMILY,
            "container_name": CONTAINER_NAME,
            "launch_type": "FARGATE",
            "network_configuration": NETWORK_CONFIG,
            "awslogs_group": f"/ecs/{TASK_DEF_FAMILY}",
            "awslogs_region": AWS_REGION,
            "awslogs_stream_prefix": "ecs",
            "environment_variables": {
                "AWS_DEFAULT_REGION": AWS_REGION,
                "DBT_S3_BUCKET": S3_BUCKET,
            },
        },
    )

    delete_stack = CloudFormationDeleteStackOperator(task_id="delete_infra_stack", stack_name=STACK_NAME, trigger_rule="all_done")

    cleanup_old >> create_stack >> wait_stack >> build_image >> seed_data >> dbt_models >> delete_stack
