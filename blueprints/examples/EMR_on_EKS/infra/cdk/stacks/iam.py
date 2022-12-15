import os
import aws_cdk.aws_iam as aws_iam
from constructs import Construct


def create_emr_eks_role(
    scope: Construct, 
    constructid, 
    data_bucket_arn: str, 
    region: str, 
    account: str) -> aws_iam.Role:

    emr_eks_policy_document = aws_iam.PolicyDocument(
        statements=[
            aws_iam.PolicyStatement(
                actions=[
                    "s3:PutObject",
                    "s3:DeleteObject",
                    "s3:GetObject",
                    "s3:ListBucket",
                ],
                effect=aws_iam.Effect.ALLOW,
                resources=[
                    f'{data_bucket_arn}/*',
                    f'{data_bucket_arn}'
                ]
            ),
            aws_iam.PolicyStatement(
                actions=[
                    "logs:CreateLogStream",
                    "logs:CreateLogGroup",
                    "logs:PutLogEvents",
                    "logs:DescribeLogGroups",
                    "logs:DescribeLogStreams"
                ],
                effect=aws_iam.Effect.ALLOW,
                resources=[f"arn:aws:logs:{region}:{account}:log-group:*", f"arn:aws:logs:{region}:{account}:log-group:*:log-stream:*"],
            )
            
        ]
    )

    r = aws_iam.Role(
        scope,
        "virtualcluster_role",
        assumed_by=aws_iam.CompositePrincipal(
            aws_iam.ServicePrincipal("elasticmapreduce.amazonaws.com"),
            aws_iam.ServicePrincipal("ec2.amazonaws.com"),
        ),
        inline_policies={"CDKmwaaPolicyDocument": emr_eks_policy_document},
    )

    return r

def create_emr_eks_mwaa_policy(
    scope: Construct, 
    constructid, 
    virtual_cluster_role_arn: str, 
    data_bucket_name:str,
    region: str, 
    account: str) -> aws_iam.Policy:

    emr_eks_policy_document = aws_iam.PolicyDocument(
        statements=[
            aws_iam.PolicyStatement(
                actions=[
                    "emr-containers:StartJobRun",
                    "emr-containers:DescribeJobRun",
                    "emr-containers:ListJobRuns",
                    "emr-containers:CancelJobRun"
                ],
                effect=aws_iam.Effect.ALLOW,
                resources=[
                    f"arn:aws:emr-containers:{region}:{account}:/*",
                    f"arn:aws:emr-containers:{region}:{account}:/virtualclusters/*/jobruns/*"
                ]
            ),
            aws_iam.PolicyStatement(
                actions=[
                    "iam:PassRole",
                ],
                effect=aws_iam.Effect.ALLOW,
                resources=[
                    virtual_cluster_role_arn
                    
                ]
            ),
            aws_iam.PolicyStatement(
                actions=[
                "s3:GetObject",
                "s3:ListBucket"
                ],
                effect=aws_iam.Effect.ALLOW,
                resources=[
                    "arn:aws:s3:::noaa-ghcn-pds/*",
                    "arn:aws:s3:::noaa-ghcn-pds"
                    
                ]
            ),
            aws_iam.PolicyStatement(
                actions=[
                "s3:PutObject*",
                "s3:ListBucket"
                ],
                effect=aws_iam.Effect.ALLOW,
                resources=[
                    f"arn:aws:s3:::{data_bucket_name}/*",
                    f"arn:aws:s3:::{data_bucket_name}"
                    
                ]
            )

        ]
    )

    policy = aws_iam.ManagedPolicy(
        scope,
        "mwaa_emr_on_eks_policy",
        document= emr_eks_policy_document,
        
    )

    return policy
