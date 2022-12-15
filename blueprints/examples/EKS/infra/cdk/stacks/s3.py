from aws_cdk import (
    aws_ec2,
    aws_s3,
    aws_ssm,
    RemovalPolicy,
    Stack
)
from constructs import Construct
from .common import constants


class S3Stack(Stack):
    @property
    def bucket(self) -> aws_s3.Bucket:
        return self._bucket

    def __init__(self, scope: Construct, construct_id: str, vpc: aws_ec2.Vpc, bucket_name: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        create_s3_vpc_gateway_endpoint(self, construct_id, vpc)
        self._bucket = create_private_bucket_deploy_dag(self, construct_id,
                                                        bucket_name=bucket_name,
                                                        versioned=True
                                                        )


def create_private_bucket_deploy_dag(
        scope: Construct,
        construct_id: str,
        bucket_name: str,
        versioned: bool) -> aws_s3.Bucket:
    # create S3 bucket
    b = aws_s3.Bucket(
        scope,
        id=f'{construct_id}-bucket',
        bucket_name=bucket_name,
        versioned=versioned,
        block_public_access=aws_s3.BlockPublicAccess.BLOCK_ALL,
        removal_policy=RemovalPolicy.DESTROY
    )

    # store the s3 bucket arn in SSM Parameter for future use
    aws_ssm.StringParameter(
        scope,
        'ssm-eks-cluster-param',
        parameter_name=f'/{constants.ID}/bucket-arn',
        string_value=b.bucket_arn,
        description='S3 Bucket ARN'
    )

    return b


def create_s3_vpc_gateway_endpoint(scope: Construct, id: str, vpc: aws_ec2.Vpc):
    aws_ec2.GatewayVpcEndpoint(
        scope,
        vpc=vpc,
        id=f'{id}-s3-gateway-endpoint',
        subnets=[aws_ec2.SubnetSelection(subnet_type=aws_ec2.SubnetType.PRIVATE_WITH_EGRESS)],
        service=aws_ec2.GatewayVpcEndpointAwsService.S3
    )
