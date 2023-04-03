"""
-*- coding: utf-8 -*-
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is furnished to do so.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
# FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
# COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
# IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

from aws_cdk import(
    aws_ec2 as ec2,
    aws_ssm as ssm,
    Stack,
    CfnOutput
)
from constructs import Construct

class MWAAInfraStack(Stack):
    """
    This class contains the methods
    for creation of VPC, and required
    Network configuration for running MWAA.
    """
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        # VPC for MWAA
        self.airflow_vpc = ec2.Vpc(
            self,
            id="airflow-vpc",
            cidr="10.0.0.0/16",
            vpc_name="airflow-vpc",
            max_azs=3,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="airflow-public", cidr_mask=24,
                    reserved=False, subnet_type=ec2.SubnetType.PUBLIC),
                ec2.SubnetConfiguration(
                    name="airflow-private", cidr_mask=24,
                    reserved=False, subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)
            ],
            enable_dns_hostnames=True,
            enable_dns_support=True
        )
        # Export VPC Id
        CfnOutput(self, id="VPCId", value=self.airflow_vpc.vpc_id, \
            description="MWAA VPC ID", export_name=f"MWAA:vpc-id")
        # Export Subnet
        CfnOutput(self, id="SubnetIds", value=','.join(self.airflow_vpc.select_subnets( \
                subnet_type=ec2.SubnetType.PRIVATE_WITH_NAT).subnet_ids), \
                description="MWAA Subnet IDs", export_name=f"MWAA:subnet-ids")
        # Export Security Group
        CfnOutput(self, id="AirflowSecurityGroup", value=self.airflow_vpc.vpc_default_security_group, \
            description="MWAA Security Group", export_name=f"MWAA:security-group")
