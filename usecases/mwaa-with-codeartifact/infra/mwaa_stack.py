import os

from aws_cdk import aws_mwaa as mwaa, aws_iam as iam, CfnJson, Stack
from constructs import Construct
from infra.s3_stack import S3Stack
from infra.vpc_stack import VpcStack


class MwaaStack(Stack):
    def __init__(
        self, scope: Construct, id: str, vpc: VpcStack, s3: S3Stack, **kwargs
    ) -> None:
        super().__init__(scope, id, **kwargs)

        mwaa_env_name = "mwaa_codeartifact_env"
        airflow_version = os.environ.get("AIRFLOW_VERSION", "2.0.2")

        # Create MWAA role
        mwaa_role = iam.Role(
            self,
            "MWAARole",
            assumed_by=iam.ServicePrincipal("airflow-env.amazonaws.com"),
        )
        mwaa_role.add_to_policy(
            iam.PolicyStatement(
                resources=[
                    (
                        f"arn:aws:airflow:{self.region}:"
                        f"{self.account}:environment/{mwaa_env_name}"
                    )
                ],
                actions=["airflow:PublishMetrics"],
                effect=iam.Effect.ALLOW,
            )
        )
        mwaa_role.add_to_policy(
            iam.PolicyStatement(
                resources=[
                    f"arn:aws:s3:::{s3.instance.bucket_name}",
                    f"arn:aws:s3:::{s3.instance.bucket_name}/*",
                ],
                actions=["s3:ListAllMyBuckets"],
                effect=iam.Effect.DENY,
            )
        )
        mwaa_role.add_to_policy(
            iam.PolicyStatement(
                resources=[
                    f"arn:aws:s3:::{s3.instance.bucket_name}",
                    f"arn:aws:s3:::{s3.instance.bucket_name}/*",
                ],
                actions=["s3:*"],
                effect=iam.Effect.ALLOW,
            )
        )
        mwaa_role.add_to_policy(
            iam.PolicyStatement(
                resources=[
                    (
                        f"arn:aws:logs:{self.region}:{self.account}:"
                        f"log-group:airflow-{mwaa_env_name}-*"
                    )
                ],
                actions=[
                    "logs:CreateLogStream",
                    "logs:CreateLogGroup",
                    "logs:PutLogEvents",
                    "logs:GetLogEvents",
                    "logs:GetLogRecord",
                    "logs:GetLogGroupFields",
                    "logs:GetQueryResults",
                    "logs:DescribeLogGroups",
                ],
                effect=iam.Effect.ALLOW,
            )
        )
        mwaa_role.add_to_policy(
            iam.PolicyStatement(
                resources=["*"],
                actions=["cloudwatch:PutMetricData"],
                effect=iam.Effect.ALLOW,
            )
        )
        mwaa_role.add_to_policy(
            iam.PolicyStatement(
                resources=[f"arn:aws:sqs:{self.region}:*:airflow-celery-*"],
                actions=[
                    "sqs:ChangeMessageVisibility",
                    "sqs:DeleteMessage",
                    "sqs:GetQueueAttributes",
                    "sqs:GetQueueUrl",
                    "sqs:ReceiveMessage",
                    "sqs:SendMessage",
                ],
                effect=iam.Effect.ALLOW,
            )
        )
        string_like = CfnJson(
            self,
            "ConditionJson",
            value={f"kms:ViaService": f"sqs.{self.region}.amazonaws.com"},
        )
        mwaa_role.add_to_policy(
            iam.PolicyStatement(
                not_resources=[f"arn:aws:kms:*:{self.account}:key/*"],
                actions=[
                    "kms:Decrypt",
                    "kms:DescribeKey",
                    "kms:GenerateDataKey*",
                    "kms:Encrypt",
                ],
                effect=iam.Effect.ALLOW,
                conditions={"StringLike": string_like},
            )
        )

        # Define MWAA configuration
        security_group_ids = mwaa.CfnEnvironment.NetworkConfigurationProperty(
            security_group_ids=[vpc.mwaa_sg.security_group_id],
            subnet_ids=vpc.get_vpc_private_subnet_ids,
        )

        logs_conf = mwaa.CfnEnvironment.ModuleLoggingConfigurationProperty(
            enabled=True, log_level="INFO"
        )

        logging_configuration = mwaa.CfnEnvironment.LoggingConfigurationProperty(
            scheduler_logs=logs_conf,
            webserver_logs=logs_conf,
            dag_processing_logs=logs_conf,
        )

        # Create MWAA environment
        mwaa_ca_env = mwaa.CfnEnvironment(
            self,
            "mwaa_ca_env",
            name=mwaa_env_name,
            environment_class="mw1.small",
            airflow_version=airflow_version,
            execution_role_arn=mwaa_role.role_arn,
            source_bucket_arn=s3.instance.bucket_arn,
            dag_s3_path="dags",
            requirements_s3_path="requirements.txt",
            max_workers=2,
            webserver_access_mode="PUBLIC_ONLY",
            network_configuration=security_group_ids,
            logging_configuration=logging_configuration,
        )
        mwaa_ca_env.node.add_dependency(mwaa_role)
