import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from constructs import Construct
from typing import List


class VpcStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        self._instance = ec2.Vpc(
            self,
            "mwaa-vpc",
            max_azs=2,
            ip_addresses=ec2.IpAddresses.cidr("10.0.0.0/16"),
            subnet_configuration=self.subnets,
            enable_dns_hostnames=True,
            enable_dns_support=True,
        )

        self.create_security_groups()
        self.create_endpoints()
        self.tag_subnets()
        cdk.CfnOutput(self, "Output", value=self._instance.vpc_id)

    @property
    def instance(self) -> ec2.Vpc:
        return self._instance

    @property
    def get_vpc_private_subnet_ids(self) -> List[str]:
        return self.instance.select_subnets(
            subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
        ).subnet_ids

    @property
    def subnets(self) -> List[ec2.SubnetConfiguration]:
        return [
            ec2.SubnetConfiguration(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED, 
                name="mwaa-private", 
                cidr_mask=24
            ),
        ]

    def create_security_groups(self) -> None:
        self.mwaa_sg = ec2.SecurityGroup(
            self,
            "mwaa-sg-cdk",
            security_group_name="mwaa-sg-cdk",
            description="MWAA SG",
            vpc=self.instance,
            allow_all_outbound=True,
        )

        self.mwaa_sg.connections.allow_from(
            self.mwaa_sg, ec2.Port.all_traffic(), "Ingress"
        )

    def create_endpoints(self) -> None:
        endpoints = {
            "SQS": ec2.InterfaceVpcEndpointAwsService.SQS,
            "CLOUDWATCH_LOGS": ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS,
            "CLOUDWATCH_MONITORING": ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH,
            "KMS ": ec2.InterfaceVpcEndpointAwsService.KMS,
            "ECR": ec2.InterfaceVpcEndpointAwsService.ECR,
            "ECR_DOCKER": ec2.InterfaceVpcEndpointAwsService.ECR_DOCKER,
            "CODE_ARTIFACT_API": ec2.InterfaceVpcEndpointAwsService(
                name="codeartifact.api"
            ),
            "CODE_ARTIFACT_REPOSITORIES": ec2.InterfaceVpcEndpointAwsService(
                name="codeartifact.repositories"
            ),
        }

        for name, service in endpoints.items():
            ec2.InterfaceVpcEndpoint(
                self,
                name,
                vpc=self.instance,
                service=service,
                subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
                private_dns_enabled=True,
                security_groups=[self.mwaa_sg],
            )

        self.instance.add_gateway_endpoint(
            "s3-endpoint",
            service=ec2.GatewayVpcEndpointAwsService.S3,
            subnets=[ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED)],
        )

    def tag_subnets(self) -> None:
        selection = self.instance.select_subnets(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED)
        for subnet in selection.subnets:
            cdk.Tags.of(subnet).add("Name", f"mwaa-private-{subnet.availability_zone}")
        cdk.Tags.of(self.instance).add("Name", "private-mwaa-vpc")