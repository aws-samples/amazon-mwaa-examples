from aws_cdk import Stack, aws_s3, aws_s3_deployment
from constructs import Construct


class S3SDeploytack(Stack):
    def __init__(self, scope: Construct, construct_id: str, bucket: aws_s3.Bucket, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        aws_s3_deployment.BucketDeployment(self, "DeployDAG",
                                           sources=[aws_s3_deployment.Source.asset("../../dags")],
                                           destination_bucket=bucket,
                                           destination_key_prefix="dags",
                                           prune=False,
                                           retain_on_delete=False
                                           )
