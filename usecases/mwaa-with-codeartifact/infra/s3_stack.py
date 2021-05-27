import os
import secrets

from aws_cdk import aws_s3 as s3, core
from aws_cdk import aws_s3_deployment as s3_deploy


class S3Stack(core.Stack):
    def __init__(self, scope: core.Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        rand_int = secrets.randbelow(1000001)
        self._instance = s3.Bucket(
            self,
            "mwaa-ca-bucket",
            bucket_name=os.environ.get("BUCKET_NAME", f"mwaa-ca-{rand_int}"),
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=core.RemovalPolicy.DESTROY,
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
    def instance(self) -> core.Resource:
        return self._instance
