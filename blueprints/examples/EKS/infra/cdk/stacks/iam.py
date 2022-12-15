from aws_cdk import (
    aws_iam,
    RemovalPolicy
)
from constructs import Construct


def create_iam_role(
        scope: Construct,
        dags_bucket_arn: str,
        region: str,
        account: str,
        eks_cluster_name: str,
        airflow_env_name: str) -> aws_iam.Role:
    mwaa_policy_document = aws_iam.PolicyDocument(
        statements=[
            aws_iam.PolicyStatement(
                actions=[
                    'airflow:PublishMetrics',
                    'airflow:GetEnvironment'
                ],
                effect=aws_iam.Effect.ALLOW,
                resources=[f"arn:aws:airflow:{region}:{account}:environment/{airflow_env_name}"],
            ),
            aws_iam.PolicyStatement(
                actions=[
                    "s3:ListAllMyBuckets"
                ],
                effect=aws_iam.Effect.DENY,
                resources=[
                    f'{dags_bucket_arn}/*'
                    f'{dags_bucket_arn}'
                ]
            ),
            aws_iam.PolicyStatement(
                actions=[
                    "s3:GetObject*",
                    "s3:GetBucket*",
                    "s3:List*"
                ],
                effect=aws_iam.Effect.ALLOW,
                resources=[
                    f"{dags_bucket_arn}/*",
                    f"{dags_bucket_arn}"
                ],
            ),
            aws_iam.PolicyStatement(
                actions=[
                    "logs:CreateLogStream",
                    "logs:CreateLogGroup",
                    "logs:PutLogEvents",
                    "logs:GetLogEvents",
                    "logs:GetLogRecord",
                    "logs:GetLogGroupFields",
                    "logs:GetQueryResults"
                ],
                effect=aws_iam.Effect.ALLOW,
                resources=[f"arn:aws:logs:{region}:{account}:log-group:*"],
            ),
            aws_iam.PolicyStatement(
                actions=[
                    "logs:DescribeLogGroups"
                ],
                effect=aws_iam.Effect.ALLOW,
                resources=["*"],
            ),
            aws_iam.PolicyStatement(
                actions=[
                    "sqs:ChangeMessageVisibility",
                    "sqs:DeleteMessage",
                    "sqs:GetQueueAttributes",
                    "sqs:GetQueueUrl",
                    "sqs:ReceiveMessage",
                    "sqs:SendMessage"
                ],
                effect=aws_iam.Effect.ALLOW,
                resources=[f"arn:aws:sqs:{region}:*:airflow-celery-*"],
            ),
            aws_iam.PolicyStatement(
                actions=[
                    "iam:PassRole"
                ],
                effect=aws_iam.Effect.ALLOW,
                resources=[f"arn:aws:sqs:{region}:*:airflow-celery-*"],
            ),
            aws_iam.PolicyStatement(
                actions=[
                    "kms:Decrypt",
                    "kms:DescribeKey",
                    "kms:GenerateDataKey*",
                    "kms:Encrypt",
                    "kms:PutKeyPolicy"
                ],
                effect=aws_iam.Effect.ALLOW,
                resources=["*"],
                conditions={
                    "StringEquals": {
                        "kms:ViaService": [
                            f"sqs.{region}.amazonaws.com",
                            f"s3.{region}.amazonaws.com",
                        ]
                    }
                },
            ),
            aws_iam.PolicyStatement(
                actions=[
                    "eks:CreateCluster",
                    "eks:TagResource",
                    "eks:CreateNodegroup",
                    "eks:DescribeNodegroup",
                    "eks:DeleteNodegroup",
                    "eks:DeleteCluster",
                    "eks:CreateFargateProfile",
                    "eks:DeleteFargateProfile"
                ],
                effect=aws_iam.Effect.ALLOW,
                resources=[
                    f"arn:aws:eks:{region}:{account}:cluster/{eks_cluster_name}",
                    f"arn:aws:eks:{region}:{account}:cluster/{eks_cluster_name}/*",
                    f"arn:aws:eks:{region}:{account}:cluster/fargate-demo-v2",
                    f"arn:aws:eks:{region}:{account}:cluster/fargate-demo-v2/*",
                    f"arn:aws:eks:{region}:{account}:nodegroup/{eks_cluster_name}/*/*",
                    # All Node Groups within the cluster
                    f"arn:aws:eks:{region}:{account}:nodegroup/fargate-demo-v2/*/*"
                    # All Node Groups within the cluster
                ],  # TODO externalize cluster name
            ),
            aws_iam.PolicyStatement(
                actions=[
                    "eks:ListClusters"
                ],
                effect=aws_iam.Effect.ALLOW,
                resources=[f"arn:aws:eks:{region}:{account}:cluster/*"]

            ),
            aws_iam.PolicyStatement(
                actions=[
                    "ssm:GetParameter"
                ],
                effect=aws_iam.Effect.ALLOW,
                resources=[f"arn:aws:ssm:{region}:{account}:parameter/eks-airflow/*"]
            )
        ]
    )

    r = aws_iam.Role(
        scope,
        "mwaa-service-role",
        assumed_by=aws_iam.CompositePrincipal(
            aws_iam.ServicePrincipal("airflow.amazonaws.com"),
            aws_iam.ServicePrincipal("airflow-env.amazonaws.com"),
            aws_iam.ServicePrincipal("ec2.amazonaws.com"),
            aws_iam.ServicePrincipal("eks.amazonaws.com"),
            aws_iam.ServicePrincipal("eks-fargate-pods.amazonaws.com"),
            aws_iam.ServicePrincipal("eks-nodegroup.amazonaws.com"),
        ),
        inline_policies={"CDKmwaaPolicyDocument": mwaa_policy_document},
    )

    # For NodeGroup
    r.add_to_policy(
        pass_role_policy([
            r.role_arn,
            aws_iam.Role.from_role_name(
                scope,
                'AWSServiceRoleForAmazonEKSNodegroup-role',
                role_name='aws-service-role/eks-nodegroup.amazonaws.com/AWSServiceRoleForAmazonEKSNodegroup').role_arn
        ])
    )

    # For Fargate
    r.add_to_policy(
        pass_role_policy([
            r.role_arn,
            aws_iam.Role.from_role_name(scope, 'AWSServiceRoleForAmazonEKSFargate-role',
                                        'aws-service-role/eks-fargate.amazonaws.com/AWSServiceRoleForAmazonEKSForFargate').role_arn
        ])
    )

    for p in [
        'AmazonEKSClusterPolicy',
        'AmazonEKSWorkerNodePolicy',
        'AmazonEC2ContainerRegistryReadOnly',
        'AmazonEKS_CNI_Policy'
    ]:
        r.add_managed_policy(aws_iam.ManagedPolicy.from_aws_managed_policy_name(p))

    r.apply_removal_policy(
        RemovalPolicy.RETAIN)  # this will ensure that the role is not removed when the nodegroup is destroyed

    return r


def nodegroup_iam_role_and_passrole_policy(scope: Construct, runner_role: aws_iam.Role) -> aws_iam.Role:
    r = aws_iam.Role(
        scope,
        "mwaa-pod-role",
        assumed_by=aws_iam.CompositePrincipal(
            aws_iam.ServicePrincipal("airflow.amazonaws.com"),
            aws_iam.ServicePrincipal("airflow-env.amazonaws.com"),
            aws_iam.ServicePrincipal("ec2.amazonaws.com"),
            aws_iam.ServicePrincipal("eks.amazonaws.com"),
            aws_iam.ServicePrincipal("eks-fargate-pods.amazonaws.com"),
            aws_iam.ServicePrincipal("eks-nodegroup.amazonaws.com"),
        ),
    )

    # add pass role capability to the runner to node group role
    runner_role.add_to_policy(pass_role_policy([r.role_arn]))

    for p in [
        'AmazonEKSClusterPolicy',
        'AmazonEKSWorkerNodePolicy',
        'AmazonEC2ContainerRegistryReadOnly',
        'AmazonEKS_CNI_Policy'
    ]:
        r.add_managed_policy(aws_iam.ManagedPolicy.from_aws_managed_policy_name(p))

    return r


def pass_role_policy(resourceArns) -> aws_iam.PolicyStatement:
    return aws_iam.PolicyStatement(
        actions=["iam:GetRole", 'iam:PassRole', 'iam:ListAttachedRolePolicies'],
        effect=aws_iam.Effect.ALLOW,
        resources=resourceArns
    )
