import aws_cdk
from aws_cdk import (
    Stack,
    aws_ec2,
    aws_ssm
)
from constructs import Construct


class VpcStack(Stack):
    @property
    def vpc(self) -> aws_ec2.Vpc:
        return self._vpc

    def __init__(
            self,
            scope: Construct,
            construct_id: str,
            cidr: str,
            max_azs: int,
            cidr_mask: int,
            **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create VPC
        self._vpc = aws_ec2.Vpc(
            self,
            id=f'{construct_id}-vpc',
            cidr=cidr,
            max_azs=max_azs,
            subnet_configuration=[
                aws_ec2.SubnetConfiguration(
                    name='public',
                    cidr_mask=cidr_mask,
                    reserved=False,
                    subnet_type=aws_ec2.SubnetType.PUBLIC
                ),
                aws_ec2.SubnetConfiguration(
                    name='private',
                    cidr_mask=cidr_mask,
                    reserved=False,
                    subnet_type=aws_ec2.SubnetType.PRIVATE_WITH_EGRESS
                )
            ]
        )

        # create VPC Endpoints
        for svc, n in [
            [aws_ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS, 'CLOUDWATCH_LOGS'],
            [aws_ec2.InterfaceVpcEndpointAwsService.KMS, 'KMS'],
            [aws_ec2.InterfaceVpcEndpointAwsService.ECR, 'ECR'],
            [aws_ec2.InterfaceVpcEndpointAwsService.ECR_DOCKER, 'ECR_DOCKER']
        ]:
            aws_ec2.InterfaceVpcEndpoint(
                self,
                f'{construct_id}-vpce-${n}',
                vpc=self.vpc,
                service=svc,
                open=True,
                subnets=aws_ec2.SubnetSelection(subnet_type=aws_ec2.SubnetType.PRIVATE_WITH_EGRESS)
            )

        aws_cdk.CfnOutput(
            self,
            id=f'{id}-vpc-output',
            value=self.vpc.vpc_id,
            description='VPC ID',
            export_name=f'{self.region}:{self.account}:{self.stack_name}:vpc-id'
        )
