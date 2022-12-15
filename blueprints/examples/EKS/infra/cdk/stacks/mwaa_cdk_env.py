import os

from aws_cdk import (
    aws_ec2,
    aws_ssm,
    CfnOutput,
    Stack
)
from constructs import Construct

from .common import constants
from .iam import create_iam_role
from .kms import create_kms_key
from .mwaa_environment import create_mwaa_environment
from .network_configuration_and_logging import (
    create_logging_config,
    create_network_configuration
)


class MwaaCdkStackEnv(Stack):
    def __init__(self, scope: Construct, construct_id: str, vpc: aws_ec2.Vpc, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        bucket_arn = aws_ssm.StringParameter.from_string_parameter_name(
            self,
            'bucket-arn',
            string_parameter_name=f'/{constants.ID}/bucket-arn'
        ).string_value

        mwaa_role = create_iam_role(
            self, bucket_arn, self.region, self.account, constants.CLUSTER_NAME, constants.MWAA_ENV)

        # store mwaa role as SSM Parameter
        aws_ssm.StringParameter(
            self,
            'ssm-mwaa-role',
            parameter_name=f'/{constants.ID}/mwaa-role',
            description='mwaa Role ARN',
            string_value=mwaa_role.role_arn
        )

        kms_key = create_kms_key(self, construct_id=construct_id, region=self.region, account=self.account)
        logging_configuration = create_logging_config(self, construct_id)
        network_configuration = create_network_configuration(self, construct_id, vpc=vpc)

        mwaa_configuration_options = {
            'cdk.cluster_name': constants.CLUSTER_NAME,
            'cdk.vpc_id': vpc.vpc_id,
            'cdk.nodegroup_name': constants.NODEGROUP_NAME,
            'cdk.cluster_role': mwaa_role.role_arn,
            # 'cdk.nodegroup_role': , -> TODO: add this automatically
            # comma separated string of all the subnets with egress in the vpc
            'cdk.subnets': ','.join(vpc.select_subnets(subnet_type=aws_ec2.SubnetType.PRIVATE_WITH_EGRESS).subnet_ids),
            'cdk.mwaa_env': constants.MWAA_ENV,
            'core.load_default_connections': False,
            'core.load_examples': False,
            'webserver.dag_default_view': 'tree',
            'webserver.dag_orientation': 'TB',
            'core.default_timezone': 'utc',
            'core.dag_run_conf_overrides_params': True
        }

        create_mwaa_environment(
            self,
            construct_id=construct_id,
            env_name=constants.MWAA_ENV,
            mwaa_role_arn=mwaa_role.role_arn,
            kms_key_arn=kms_key.key_arn,
            logging_configuration=logging_configuration,
            network_configuration=network_configuration,
            dags_bucket_arn=bucket_arn,
            mwaa_configuration_options=mwaa_configuration_options,
            # parameters are optional. they also need vtov be uncommented in mwaa_environment: aws_mwaa.CfnEnvironment
            # plugins_s3_path=mwaa_props['plugins_file'],
            # requirements_s3_path=mwaa_props['requirements_file'] parameter is optional. uncomment if needed
        )

        # output the EKS Cluster role and NodeGroup Role ARN
        CfnOutput(self, "EKS_CLUSTER_ROLE_ARN", value=mwaa_role.role_arn)
