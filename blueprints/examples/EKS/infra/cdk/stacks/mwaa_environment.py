from aws_cdk import (
    aws_mwaa,
    aws_ssm
)
from constructs import Construct
from .common import constants


def create_mwaa_environment(
        scope: Construct,
        construct_id: str,
        env_name: str,
        mwaa_role_arn: str,
        kms_key_arn: str,
        logging_configuration: aws_mwaa.CfnEnvironment.LoggingConfigurationProperty,
        network_configuration: aws_mwaa.CfnEnvironment.NetworkConfigurationProperty,
        dags_bucket_arn: str,
        mwaa_configuration_options,
        requirements_s3_path: str = None,
        plugins_s3_path: str = None
):
    tags = {
        'env': f'{constants.MWAA_ENV}',
        'service': 'MWAA Apache AirFlow'
    }

    managed_airflow = aws_mwaa.CfnEnvironment(
        scope,
        id=f'{construct_id}-environment',
        name=env_name,
        airflow_configuration_options=mwaa_configuration_options,
        airflow_version=constants.AIRFLOW_VERSION,
        dag_s3_path='dags',
        environment_class='mw1.small',
        execution_role_arn=mwaa_role_arn,
        kms_key=kms_key_arn,
        logging_configuration=logging_configuration,
        max_workers=5,
        network_configuration=network_configuration,
        # plugins_s3_path=plugins_s3_path, uncomment and provide environment variable to enable plugins file
        # requirements_s3_path=requirements_s3_path, uncomment and provide environment variable to enable plugins file
        source_bucket_arn=dags_bucket_arn,
        webserver_access_mode='PUBLIC_ONLY'
    )

    managed_airflow.add_override('Properties.Tags', tags)
