# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import aws_cdk.aws_eks as eks
import aws_cdk.aws_emrcontainers as emrc
import aws_cdk.aws_iam as iam
import aws_cdk.aws_logs as logs
import aws_cdk as core
import aws_cdk.aws_ec2 as ec2
from constructs import Construct


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
        self.emr_namespace_fg = "emr-data-team-a"
        self.emrsvcrolearn = f"arn:aws:iam::{self.account}:role/AWSServiceRoleForAmazonEMRContainers"

        self.instance_type = props['instance_types']

        self.vpc = ec2.Vpc.from_lookup(self, "VPC",
            # This imports the default VPC but you can also
            # specify a 'vpcName' or 'tags'.
            vpc_id = props['vpc_id']
        )

        core.Tags.of(self.vpc).add("for-use-with-amazon-emr-managed-policies", "true")

        # EKS cluster
        self.cluster = eks.Cluster(self, props['eks_cluster_id'],
            version=eks.KubernetesVersion.of(props['cluster_version']),
            default_capacity=0,
            endpoint_access=eks.EndpointAccess.PUBLIC_AND_PRIVATE,
            vpc=self.vpc,
            vpc_subnets=[ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_NAT)]
        )




        namespace_fg = self.cluster.add_manifest(self.emr_namespace_fg, {
            "apiVersion":"v1",
            "kind":"Namespace",
            "metadata":{"name": self.emr_namespace_fg},
        })

        fgprofile = eks.FargateProfile(self, "SparkFargateProfile", cluster=self.cluster, 
            selectors=[{"namespace": self.emr_namespace_fg}]
        )

        emrrole_fg = self.cluster.add_manifest("emrrole_fg", {
            "apiVersion":"rbac.authorization.k8s.io/v1",
            "kind":"Role",
            "metadata":{"name": "emr-containers", "namespace": self.emr_namespace_fg},
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
        emrrole_fg.node.add_dependency(namespace_fg)


        emrrolebind_fg = self.cluster.add_manifest("emrrolebind_fg", {
            "apiVersion":"rbac.authorization.k8s.io/v1",
            "kind":"RoleBinding",
            "metadata":{"name": "emr-containers", "namespace": self.emr_namespace_fg},
            "subjects":[{"kind": "User","name":"emr-containers","apiGroup": "rbac.authorization.k8s.io"}],
            "roleRef":{"kind":"Role","name":"emr-containers","apiGroup": "rbac.authorization.k8s.io"}
        })
        emrrolebind_fg.node.add_dependency(emrrole_fg)

        # Map user to IAM role
        emrsvcrole = iam.Role.from_role_arn(self, "EmrSvcRole", self.emrsvcrolearn, mutable=False)
        self.cluster.aws_auth.add_role_mapping(emrsvcrole, groups=[], username="emr-containers")

         # Job execution role
        self.job_role = iam.Role(self, "EMR_EKS_Job_Role", assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonS3FullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEC2FullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("CloudWatchFullAccess")])
        core.CfnOutput(
            self, "JobRoleArn",
            value=self.job_role.role_arn
        )

        # Modify trust policy
        string_like = core.CfnJson(self, "ConditionJson",
            value={
                f"{self.cluster.cluster_open_id_connect_issuer}:sub": f"system:serviceaccount:emr:emr-containers-sa-*-*-{self.account}-*"
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

        emr_vc_fg = emrc.CfnVirtualCluster(scope=self,
            id="EMRClusterFG",
            container_provider=emrc.CfnVirtualCluster.ContainerProviderProperty(id=self.cluster.cluster_name,
                info=emrc.CfnVirtualCluster.ContainerInfoProperty(eks_info=emrc.CfnVirtualCluster.EksInfoProperty(namespace=self.emr_namespace_fg)),
                type="EKS"
            ),
            name="EMRClusterFG"
        )
        emr_vc_fg.node.add_dependency(namespace_fg) 
        emr_vc_fg.node.add_dependency(emrrolebind_fg) 
        core.CfnOutput(
            self, "VirtualClusterId",
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

