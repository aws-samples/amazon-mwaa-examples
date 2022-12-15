# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import aws_cdk.aws_eks as eks
import aws_cdk.aws_emrcontainers as emrc
import aws_cdk.aws_iam as iam
import aws_cdk.aws_logs as logs
import aws_cdk as core
import aws_cdk.aws_ec2 as ec2
from constructs import Construct
from stacks.iam import create_emr_eks_role, create_emr_eks_mwaa_policy
import aws_cdk.aws_s3 as aws_s3


"""
This stack deploys the following:
- VPC
- EKS cluster
- EKS configuration to support EMR on EKS
- EMR on EKS virtual cluster
- CloudWatch log group
"""
class EmrEksCdkStack(core.Stack):


    def __init__(self, scope: Construct, construct_id: str, props, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.emr_namespace = "emr-data-team-a"
        self.emrsvcrolearn = f"arn:aws:iam::{self.account}:role/AWSServiceRoleForAmazonEMRContainers"

        self.instance_type = self.node.try_get_context('instance_types')

        self.vpc = ec2.Vpc.from_lookup(self, "VPC",
            # This imports the default VPC but you can also
            # specify a 'vpcName' or 'tags'.
            vpc_id = self.node.try_get_context('vpc_id')
        )

        core.Tags.of(self.vpc).add("for-use-with-amazon-emr-managed-policies", "true")

        # EKS cluster
        self.cluster = eks.Cluster(self, self.node.try_get_context('eks_cluster_id'),
            version=eks.KubernetesVersion.of(self.node.try_get_context('cluster_version')),
            default_capacity=0,
            endpoint_access=eks.EndpointAccess.PUBLIC_AND_PRIVATE,
            vpc=self.vpc,
            vpc_subnets=[ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_NAT)]
        )

        self.data_bucket = aws_s3.Bucket(
            self,
            id='databucket',
            block_public_access=aws_s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=core.RemovalPolicy.DESTROY
        )

        # Default node group
        self.ng = self.cluster.add_nodegroup_capacity("base-node-group",
            instance_types=[ec2.InstanceType(self.instance_type)],
            min_size=3,
            max_size=10,
            disk_size=50
        )

        # Create namespaces for EMR to use
        namespace = self.cluster.add_manifest(self.emr_namespace, {
            "apiVersion":"v1",
            "kind":"Namespace",
            "metadata":{"name": self.emr_namespace},
        })

        # Create k8s cluster role for EMR
        emrrole = self.cluster.add_manifest("emrrole", {
            "apiVersion":"rbac.authorization.k8s.io/v1",
            "kind":"Role",
            "metadata":{"name": "emr-containers", "namespace": self.emr_namespace},
            "rules": [
                {"apiGroups": [""], "resources":["namespaces"],"verbs":["get"]},
                {"apiGroups": [""], "resources":["serviceaccounts", "services", "configmaps", "events", "pods", "pods/log"],"verbs":["get", "list", "watch", "describe", "create", "edit", "delete", "deletecollection", "annotate", "patch", "label"]},
                {"apiGroups": [""], "resources":["secrets"],"verbs":["create", "patch", "delete", "watch"]},
                {"apiGroups": ["apps"], "resources":["statefulsets", "deployments"],"verbs":["get", "list", "watch", "describe", "create", "edit", "delete", "annotate", "patch", "label"]},
                {"apiGroups": ["batch"], "resources":["jobs"],"verbs":["get", "list", "watch", "describe", "create", "edit", "delete", "annotate", "patch", "label"]},
                {"apiGroups": ["extensions"], "resources":["ingresses"],"verbs":["get", "list", "watch", "describe", "create", "edit", "delete", "annotate", "patch", "label"]},
                {"apiGroups": ["rbac.authorization.k8s.io"], "resources":["roles", "rolebindings"],"verbs":["get", "list", "watch", "describe", "create", "edit", "delete", "deletecollection", "annotate", "patch", "label"]}
            ]
        })
        emrrole.node.add_dependency(namespace)
        # Bind cluster role to user
        emrrolebind = self.cluster.add_manifest("emrrolebind", {
            "apiVersion":"rbac.authorization.k8s.io/v1",
            "kind":"RoleBinding",
            "metadata":{"name": "emr-containers", "namespace": self.emr_namespace},
            "subjects":[{"kind": "User","name":"emr-containers","apiGroup": "rbac.authorization.k8s.io"}],
            "roleRef":{"kind":"Role","name":"emr-containers","apiGroup": "rbac.authorization.k8s.io"}
        })
        emrrolebind.node.add_dependency(emrrole)
        # Map user to IAM role
        emrsvcrole = iam.Role.from_role_arn(self, "EmrSvcRole", self.emrsvcrolearn, mutable=False)
        
        self.cluster.aws_auth.add_role_mapping(emrsvcrole, groups=[], username="emr-containers")

         # Job execution role
        self.job_role = create_emr_eks_role(self,construct_id, self.data_bucket.bucket_arn, self.region, self.account)
        
        self.mwaa_emr_container_policy = create_emr_eks_mwaa_policy(self,construct_id, self.job_role.role_arn, self.data_bucket.bucket_name, self.region, self.account)

        core.CfnOutput(
            self, "emr_on_eks_role_arn",
            value=self.job_role.role_arn
        )

        core.CfnOutput(
            self, "emr_on_eks_mwaa_iam_policy_arn",
            value=self.mwaa_emr_container_policy.managed_policy_arn
        )
        core.CfnOutput(
            self, "emr_on_eks_data_bucket",
            value=self.data_bucket.bucket_name
        )
        
        # Modify trust policy
        string_like = core.CfnJson(self, "ConditionJson",
            value={
                f"{self.cluster.cluster_open_id_connect_issuer}:sub": f"system:serviceaccount:{self.emr_namespace}:emr-containers-sa-*-*-{self.account}-*"
            }
        )
        self.job_role.assume_role_policy.add_statements(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["sts:AssumeRoleWithWebIdentity"],
                principals=[iam.OpenIdConnectPrincipal(self.cluster.open_id_connect_provider, conditions={"StringLike": string_like})]
            )
        )
        string_aud = core.CfnJson(self, "ConditionJsonAud",
            value={
                f"{self.cluster.cluster_open_id_connect_issuer}:aud": "sts.amazon.com"
            }
        )
        self.job_role.assume_role_policy.add_statements(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["sts:AssumeRoleWithWebIdentity"],
                principals=[iam.OpenIdConnectPrincipal(self.cluster.open_id_connect_provider, conditions={"StringEquals": string_aud})]
            )
        )

         # EMR virtual cluster
        self.emr_vc = emrc.CfnVirtualCluster(scope=self,
            id="EMRCluster",
            container_provider=emrc.CfnVirtualCluster.ContainerProviderProperty(id=self.cluster.cluster_name,
                info=emrc.CfnVirtualCluster.ContainerInfoProperty(eks_info=emrc.CfnVirtualCluster.EksInfoProperty(namespace=self.emr_namespace)),
                type="EKS"
            ),
            name="EMRCluster"
        )
        self.emr_vc.node.add_dependency(namespace) 
        self.emr_vc.node.add_dependency(emrrolebind) 
        # emr_vc_fg = emrc.CfnVirtualCluster(scope=self,
        #     id="EMRClusterFG",
        #     container_provider=emrc.CfnVirtualCluster.ContainerProviderProperty(id=self.cluster.cluster_name,
        #         info=emrc.CfnVirtualCluster.ContainerInfoProperty(eks_info=emrc.CfnVirtualCluster.EksInfoProperty(namespace=self.emr_namespace_fg)),
        #         type="EKS"
        #     ),
        #     name="EMRClusterFG"
        # )
        # emr_vc_fg.node.add_dependency(namespace_fg) 
        # emr_vc_fg.node.add_dependency(emrrolebind_fg) 
        core.CfnOutput(
            self, "emrcontainers_virtual_cluster_id",
            value=self.emr_vc.attr_id
        )
        # core.CfnOutput(
        #     self, "FgVirtualClusterId",
        #     value=emr_vc_fg.attr_id
        # )

        # Create log group
        log_group = logs.LogGroup(self, "LogGroup") 
        core.CfnOutput(
            self, "LogGroupName",
            value=log_group.log_group_name
        )

