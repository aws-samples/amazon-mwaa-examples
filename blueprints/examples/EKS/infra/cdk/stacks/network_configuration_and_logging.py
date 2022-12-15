from aws_cdk import (
    aws_ec2,
    aws_mwaa,
    CfnOutput
)

from constructs import Construct


def create_network_configuration(scope: Construct, id: str,
                                 vpc: aws_ec2.Vpc) -> aws_mwaa.CfnEnvironment.NetworkConfigurationProperty:
    security_group = aws_ec2.SecurityGroup(
        scope,
        id=f'{id}-sg',
        vpc=vpc,
    )

    security_group_id = security_group.security_group_id
    security_group.connections.allow_internally(aws_ec2.Port.all_traffic(), f'{id}-sg-connection')

    return aws_mwaa.CfnEnvironment.NetworkConfigurationProperty(
        security_group_ids=[security_group_id],
        subnet_ids=vpc.select_subnets(subnet_type=aws_ec2.SubnetType.PRIVATE_WITH_EGRESS).subnet_ids
    )


def create_logging_config(scope: Construct, id: str) -> aws_mwaa.CfnEnvironment.LoggingConfigurationProperty:
    debug_logging_configuration_property = aws_mwaa.CfnEnvironment.ModuleLoggingConfigurationProperty(
        enabled=True,
        log_level='INFO'
    )

    return aws_mwaa.CfnEnvironment.LoggingConfigurationProperty(
        task_logs=debug_logging_configuration_property,
        worker_logs=debug_logging_configuration_property,
        scheduler_logs=debug_logging_configuration_property,
        dag_processing_logs=debug_logging_configuration_property,
        webserver_logs=debug_logging_configuration_property,
    )


def network_output(scope: Construct, id: str, security_group_id: str):
    CfnOutput(
        scope=scope,
        id=f'{id}-mwaa-sg',
        value=security_group_id,
        description='security group name for MWAA'
    )
