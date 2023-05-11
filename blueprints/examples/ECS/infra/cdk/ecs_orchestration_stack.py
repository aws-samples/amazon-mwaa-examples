"""
-*- coding: utf-8 -*-
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
"""
from aws_cdk import (
    aws_iam as iam,
    aws_ec2 as ec2,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
    aws_mwaa as mwaa,
    aws_kms as kms,
    aws_ecs as ecs,
    Stack,
    CfnOutput,
    Tags
)
from aws_cdk.aws_ecr_assets import DockerImageAsset, NetworkMode
from constructs import Construct
from .common import constants

class MWAAOrchestrationStack(Stack):
    def __init__(self, scope: Construct, construct_id: str,vpc,env,**kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        # Create S3 Bucket for storing dags
        s3_tags = {
            'app': f"{self.stack_name}"
        }
        dags_bucket = s3.Bucket(
            self,
            "mwaa-dags",
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL
        )
        for tag in s3_tags:
            Tags.of(dags_bucket).add(tag, s3_tags[tag])
        # Deploy dags
        s3deploy.BucketDeployment(self, "DeployDAG",
        sources=[s3deploy.Source.asset("./mwaa/dags/")],
        destination_bucket=dags_bucket,
        destination_key_prefix="airflow/dags/",
        prune=False,
        retain_on_delete=False
        )
        # Deploy requirements
        s3deploy.BucketDeployment(self, "DeployRequirements",
        sources=[s3deploy.Source.asset("./mwaa/requirements/")],
        destination_bucket=dags_bucket,
        destination_key_prefix="airflow/requirements/",
        prune=False,
        retain_on_delete=False
        )
        dags_bucket_arn = dags_bucket.bucket_arn
        # Create MWAA IAM Policies and Roles, copied from MWAA documentation site
        # After destroy remove cloudwatch log groups, S3 bucket and verify KMS key is removed.
        mwaa_policy_document = iam.PolicyDocument(
            statements=[
                iam.PolicyStatement(
                    actions=["airflow:PublishMetrics"],
                    effect=iam.Effect.ALLOW,
                    resources=[f"arn:aws:airflow:{self.region}:{self.account}:environment/{self.stack_name}"],
                ),
                iam.PolicyStatement(
                    actions=[
                        "s3:ListAllMyBuckets"
                    ],
                    effect=iam.Effect.DENY,
                    resources=[
                        f"{dags_bucket_arn}/*",
                        f"{dags_bucket_arn}"
                        ],
                ),
                iam.PolicyStatement(
                    actions=[
                        "s3:*"
                    ],
                    effect=iam.Effect.ALLOW,
                    resources=[
                        f"{dags_bucket_arn}/*",
                        f"{dags_bucket_arn}"
                        ],
                ),
                iam.PolicyStatement(
                    actions=[
                        "logs:CreateLogStream",
                        "logs:CreateLogGroup",
                        "logs:PutLogEvents",
                        "logs:GetLogEvents",
                        "logs:GetLogRecord",
                        "logs:GetLogGroupFields",
                        "logs:GetQueryResults",
                        "logs:DescribeLogGroups"
                    ],
                    effect=iam.Effect.ALLOW,
                    resources=[f"arn:aws:logs:{self.region}:{self.account}:log-group:airflow-{self.stack_name}-*"],
                ),
                iam.PolicyStatement(
                    actions=[
                        "logs:DescribeLogGroups"
                    ],
                    effect=iam.Effect.ALLOW,
                    resources=["*"],
                ),
                iam.PolicyStatement(
                    actions=[
                        "sqs:ChangeMessageVisibility",
                        "sqs:DeleteMessage",
                        "sqs:GetQueueAttributes",
                        "sqs:GetQueueUrl",
                        "sqs:ReceiveMessage",
                        "sqs:SendMessage"
                    ],
                    effect=iam.Effect.ALLOW,
                    resources=[f"arn:aws:sqs:{self.region}:*:airflow-celery-*"],
                ),
                iam.PolicyStatement(
                    actions=[
                        "ecs:RunTask",
                        "ecs:DescribeTasks",
                        "ecs:RegisterTaskDefinition",
                        "ecs:DescribeTaskDefinition",
                        "ecs:ListTasks",
                        "ecs:CreateCluster",
                        "ecs:CreateTaskSet",
                        "ecs:DeleteCluster",
                        "ecs:DeleteTaskDefinitions",
                        "ecs:StartTask",
                        "ecs:DescribeClusters",
                        "ecs:DeregisterTaskDefinition"
                    ],
                    effect=iam.Effect.ALLOW,
                    resources=[
                        "*"
                        ],
                    ),
                iam.PolicyStatement(
                    actions=[
                        "iam:PassRole"
                    ],
                    effect=iam.Effect.ALLOW,
                    resources=[ "*" ],
                    conditions= { "StringLike": { "iam:PassedToService": "ecs-tasks.amazonaws.com" } },
                    ),
                iam.PolicyStatement(
                    actions=[
                        "kms:Decrypt",
                        "kms:DescribeKey",
                        "kms:GenerateDataKey*",
                        "kms:Encrypt",
                        "kms:PutKeyPolicy"
                    ],
                    effect=iam.Effect.ALLOW,
                    resources=["*"],
                    conditions={
                        "StringEquals": {
                            "kms:ViaService": [
                                f"sqs.{self.region}.amazonaws.com",
                                f"s3.{self.region}.amazonaws.com",
                            ]
                        }
                    },
                ),
            ]
        )
        mwaa_service_role = iam.Role(
            self,
            "mwaa-service-role",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("airflow.amazonaws.com"),
                iam.ServicePrincipal("airflow-env.amazonaws.com"),
                iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            ),
            inline_policies={"CDKmwaaPolicyDocument": mwaa_policy_document},
            path="/service-role/"
        )
        # Create MWAA Security Group and get networking info
        security_group = ec2.SecurityGroup(
            self,
            id = "mwaa-sg",
            vpc = vpc,
            security_group_name = "mwaa-sg"
        )

        security_group_id = security_group.security_group_id

        security_group.connections.allow_internally(ec2.Port.all_traffic(),"MWAA")

        subnets = [subnet.subnet_id for subnet in vpc.private_subnets]
        network_configuration = mwaa.CfnEnvironment.NetworkConfigurationProperty(
            security_group_ids=[security_group_id],
            subnet_ids=subnets,
        )
        # **OPTIONAL** Configure specific MWAA settings - you can externalise these if you want
        logging_configuration = mwaa.CfnEnvironment.LoggingConfigurationProperty(
            dag_processing_logs=mwaa.CfnEnvironment.ModuleLoggingConfigurationProperty(
                enabled=True,
                log_level="INFO"
            ),
            task_logs=mwaa.CfnEnvironment.ModuleLoggingConfigurationProperty(
                enabled=True,
                log_level="INFO"
            ),
            worker_logs=mwaa.CfnEnvironment.ModuleLoggingConfigurationProperty(
                enabled=True,
                log_level="INFO"
            ),
            scheduler_logs=mwaa.CfnEnvironment.ModuleLoggingConfigurationProperty(
                enabled=True,
                log_level="INFO"
            ),
            webserver_logs=mwaa.CfnEnvironment.ModuleLoggingConfigurationProperty(
                enabled=True,
                log_level="INFO"
            )
        )
        options = {
            'core.load_default_connections': False,
            'core.load_examples': False,
            'webserver.dag_default_view': 'tree',
            'webserver.dag_orientation': 'TB'
        }
        tags = {
            "app": f"{self.stack_name}"
        }
        # **OPTIONAL** Create KMS key that MWAA will use for encryption
        kms_mwaa_policy_document = iam.PolicyDocument(
            statements=[
                iam.PolicyStatement(
                    actions=[
                        "kms:Create*",
                        "kms:Describe*",
                        "kms:Enable*",
                        "kms:List*",
                        "kms:Put*",
                        "kms:Decrypt*",
                        "kms:Update*",
                        "kms:Revoke*",
                        "kms:Disable*",
                        "kms:Get*",
                        "kms:Delete*",
                        "kms:ScheduleKeyDeletion",
                        "kms:GenerateDataKey*",
                        "kms:CancelKeyDeletion"
                    ],
                    principals=[
                        iam.AccountRootPrincipal(),
                        # Optional:
                        # iam.ArnPrincipal(f"arn:aws:sts::{self.account}:assumed-role/AWSReservedSSO_rest_of_SSO_account"),
                    ],
                    resources=["*"]),
                iam.PolicyStatement(
                    actions=[
                        "kms:Decrypt*",
                        "kms:Describe*",
                        "kms:GenerateDataKey*",
                        "kms:Encrypt*",
                        "kms:ReEncrypt*",
                        "kms:PutKeyPolicy"
                    ],
                    effect=iam.Effect.ALLOW,
                    resources=["*"],
                    principals=[iam.ServicePrincipal("logs.amazonaws.com", region=f"{self.region}")],
                    conditions={"ArnLike": {"kms:EncryptionContext:aws:logs:arn": f"arn:aws:logs:{self.region}:{self.account}:*"}},
                ),
            ]
        )
        key = kms.Key(
            self,
            f"{self.stack_name}Key",
            enable_key_rotation=True,
            policy=kms_mwaa_policy_document
        )
        key.add_alias(f"alias/{self.stack_name}Key")
        # Create ECR
        spark_image_assest = DockerImageAsset(self, "SparkImage",
            directory='./infra/spark_image/',
            network_mode=NetworkMode.HOST
        )
        # ECS Task execution Role
        ecs_tasks_service_role = iam.Role(
            self,
            "ecs-tasks-service-role",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("ecs-tasks.amazonaws.com")
            ),
            path="/service-role/"
        )
        # Create MWAA environment using all the info above
        mwaa_configuration_options = {
            'cdk.cluster_name': constants.CLUSTER_NAME,
            'core.default_timezone': 'utc',
            'cdk.spark_image':spark_image_assest.image_uri,
            'cdk.task_role':ecs_tasks_service_role.role_arn,
            'cdk.stack_name':self.stack_name,
            'cdk.vpc': vpc.vpc_id,
            'cdk.subnet_id':','.join([subnet.subnet_id for subnet in vpc.private_subnets]),
            'cdk.security_group': vpc.vpc_default_security_group
        }
        managed_airflow = mwaa.CfnEnvironment(
            scope=self,
            id='airflow-test-environment',
            name=f"{self.stack_name}",
            airflow_version='2.4.3',
            dag_s3_path="airflow/dags",
            environment_class='mw1.small',
            execution_role_arn=mwaa_service_role.role_arn,
            kms_key=key.key_arn,
            logging_configuration=logging_configuration,
            max_workers=5,
            network_configuration=network_configuration,
            requirements_s3_path="airflow/requirements/requirements.txt",
            source_bucket_arn=dags_bucket_arn,
            webserver_access_mode='PUBLIC_ONLY',
            airflow_configuration_options=mwaa_configuration_options
        )
        managed_airflow.add_override('Properties.AirflowConfigurationOptions', options)
        managed_airflow.add_override('Properties.Tags', tags)

        ecs_tasks_service_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AmazonECSTaskExecutionRolePolicy"))
        CfnOutput(
            self,
            id="SparkImageURI",
            value=spark_image_assest.image_uri,
            description="Spark Container image URI"
        )
