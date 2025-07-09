import os
import secrets

import aws_cdk as cdk
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3_deploy
from constructs import Construct


class S3Stack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        rand_int = secrets.randbelow(1000001)
        self._instance = s3.Bucket(
            self,
            "mwaa-ca-bucket",
            bucket_name=os.environ.get("BUCKET_NAME", f"mwaa-ca-{rand_int}"),
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=cdk.RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            versioned=True,
        )

        # Deploy files to an S3 bucket (MWAA DAGs)
        s3_deploy.BucketDeployment(
            self,
            "mwaa-dags-deployment",
            destination_bucket=self.instance,
            sources=[s3_deploy.Source.asset("./mwaa-ca-bucket-content")],
            retain_on_delete=False,
        )

    @property
    def instance(self) -> s3.Bucket:
        return self._instance