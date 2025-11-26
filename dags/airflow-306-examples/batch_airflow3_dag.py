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

Required IAM Permissions:
- batch:SubmitJob - Submit jobs to AWS Batch
- batch:DescribeJobs - Get job status and details
- batch:CreateJobQueue - Create Batch job queues
- batch:CreateJobDefinition - Create Batch job definitions
- batch:CreateComputeEnvironment - Create Batch compute environments
- batch:DescribeJobQueues - Get job queue details
- batch:DescribeJobDefinitions - Get job definition details
- batch:DescribeComputeEnvironments - Get compute environment details
- ecs:DescribeTaskDefinition - Access ECS task definitions
- iam:PassRole - Pass execution role to Batch
- logs:CreateLogGroup - Create CloudWatch log groups
- logs:CreateLogStream - Create CloudWatch log streams
- logs:PutLogEvents - Write to CloudWatch logs
"""
import os
import json
from datetime import datetime
from airflow import DAG
from airflow.models.param import Param
from airflow.providers.amazon.aws.operators.cloud_formation import (
    CloudFormationCreateStackOperator,
    CloudFormationDeleteStackOperator,
)
from airflow.providers.amazon.aws.sensors.cloud_formation import (
    CloudFormationCreateStackSensor,
    CloudFormationDeleteStackSensor,
)
from airflow.providers.amazon.aws.operators.batch import BatchOperator
from airflow.providers.amazon.aws.sensors.batch import BatchSensor
from airflow.utils.trigger_rule import TriggerRule

# CloudFormation template embedded as string
CLOUDFORMATION_TEMPLATE = """
AWSTemplateFormatVersion: '2010-09-09'
Description: 'AWS Batch resources - Job Definition, Compute Environment, and Job Queue'

Resources:
  BatchJobDefinition:
    Type: AWS::Batch::JobDefinition
    Properties:
      JobDefinitionName: batch-job-def-{{ ds_nodash }}-{{ ts_nodash | lower }}
      Type: container
      PlatformCapabilities:
        - FARGATE
      ContainerProperties:
        Image: busybox
        Command: {{ params.batch_command }}
        ExecutionRoleArn: {{ params.execution_role_arn }}
        JobRoleArn: {{ params.job_role_arn }}
        ResourceRequirements:
          - Type: VCPU
            Value: '0.25'
          - Type: MEMORY
            Value: '512'
        NetworkConfiguration:
          AssignPublicIp: ENABLED
        FargatePlatformConfiguration:
          PlatformVersion: LATEST

  BatchComputeEnvironment:
    Type: AWS::Batch::ComputeEnvironment
    Properties:
      ComputeEnvironmentName: batch-compute-env-{{ ds_nodash }}-{{ ts_nodash | lower }}
      Type: MANAGED
      State: ENABLED
      ComputeResources:
        Type: FARGATE
        MaxvCpus: 10
        Subnets:
          - {{ params.subnet1 }}
          - {{ params.subnet2 }}
        SecurityGroupIds:
          - {{ params.security_group }}

  BatchJobQueue:
    Type: AWS::Batch::JobQueue
    Properties:
      JobQueueName: batch-job-queue-{{ ds_nodash }}-{{ ts_nodash | lower }}
      State: ENABLED
      Priority: 1
      ComputeEnvironmentOrder:
        - Order: 1
          ComputeEnvironment: !Ref BatchComputeEnvironment
    DependsOn: BatchComputeEnvironment

Outputs:
  JobDefinitionArn:
    Description: ARN of the created job definition
    Value: !Ref BatchJobDefinition
  
  ComputeEnvironmentArn:
    Description: ARN of the created compute environment
    Value: !Ref BatchComputeEnvironment
  
  JobQueueArn:
    Description: ARN of the created job queue
    Value: !Ref BatchJobQueue
"""

default_args = {
    'start_date': datetime(2024, 1, 1),
    'retries': 0,
}

dag = DAG(
    'batch_dag',
    default_args=default_args,
    description='Create AWS Batch resources using CloudFormation (simple version)',
    schedule=None,
    params={
        'execution_role_arn': Param(
            default=os.environ.get('ROLE_ARN', 'arn:aws:iam::123456789012:role/BatchExecutionRole'),
            type='string',
            description='IAM role ARN for Batch job execution'
        ),
        'job_role_arn': Param(
            default=os.environ.get('ROLE_ARN', 'arn:aws:iam::123456789012:role/BatchJobRole'),
            type='string',
            description='IAM role ARN for Batch job tasks'
        ),
        'subnet1': Param(
            default=os.environ.get('SUBNET1', 'subnet-12345678'),
            type='string',
            description='First subnet ID for compute environment'
        ),
        'subnet2': Param(
            default=os.environ.get('SUBNET2', 'subnet-87654321'),
            type='string',
            description='Second subnet ID for compute environment'
        ),
        'security_group': Param(
            default=os.environ.get('SECURITY_GROUP', 'sg-12345678'),
            type='string',
            description='Security group ID for compute environment'
        ),
        'batch_command': Param(
            default='["echo", "hello world"]',
            type='string',
            description='JSON array format command for Batch job (e.g., ["echo", "hello world"])'
        )
    }
)

# Create CloudFormation stack
create_stack = CloudFormationCreateStackOperator(
    task_id='create_batch_stack',
    stack_name='batch-dag-resources-{{ ds_nodash }}-{{ ts_nodash | lower }}',
    cloudformation_parameters={
        'StackName': 'batch-dag-resources-{{ ds_nodash }}-{{ ts_nodash | lower }}',
        'TemplateBody': CLOUDFORMATION_TEMPLATE
    },
    dag=dag
)

# Wait for stack creation to complete
wait_for_stack = CloudFormationCreateStackSensor(
    task_id='wait_for_stack_creation',
    stack_name='batch-dag-resources-{{ ds_nodash }}-{{ ts_nodash | lower }}',
    timeout=1800,  # 30 minutes
    poke_interval=60,  # Check every minute
    dag=dag
)

# Submit batch job with command override
submit_batch_job = BatchOperator(
    task_id='submit_batch_job',
    job_name='batch-job-{{ ds_nodash }}-{{ ts_nodash | lower }}',
    job_queue='batch-job-queue-{{ ds_nodash }}-{{ ts_nodash | lower }}',
    job_definition='batch-job-def-{{ ds_nodash }}-{{ ts_nodash | lower }}',
    dag=dag
)

# Wait for batch job to complete
wait_for_batch_job = BatchSensor(
    task_id='wait_for_batch_job',
    job_id="{{ task_instance.xcom_pull(task_ids='submit_batch_job') }}",
    timeout=1800,
    poke_interval=30,
    dag=dag
)

# Clean up - delete stack
delete_stack = CloudFormationDeleteStackOperator(
    task_id='delete_batch_stack',
    stack_name='batch-dag-resources-{{ ds_nodash }}-{{ ts_nodash | lower }}',
    trigger_rule=TriggerRule.ALL_DONE,
    dag=dag
)

# Wait for stack deletion to complete
wait_for_deletion = CloudFormationDeleteStackSensor(
    task_id='wait_for_stack_deletion',
    stack_name='batch-dag-resources-{{ ds_nodash }}-{{ ts_nodash | lower }}',
    timeout=1800,
    poke_interval=60,
    dag=dag
)

# Task dependencies
create_stack >> wait_for_stack >> submit_batch_job >> wait_for_batch_job >> delete_stack >> wait_for_deletion
