import aws_cdk as cdk
from aws_cdk import (
    aws_events as events,
    aws_lambda as lambda_,
    aws_events_targets as targets,
    aws_iam as iam,
)
from constructs import Construct

from infra.codeartifact_stack import CodeArtifactStack
from infra.s3_stack import S3Stack


class LambdaCronStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        id: str,
        ca: CodeArtifactStack,
        s3: S3Stack,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        ca_sts_policy = iam.PolicyStatement(
            sid="sts",
            effect=iam.Effect.ALLOW,
            actions=["sts:GetServiceBearerToken"],
            resources=["*"],
            conditions={
                "StringEquals": {"sts:AWSServiceName": "codeartifact.amazonaws.com"},
            },
        )
        ca_token_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "codeartifact:GetAuthorizationToken",
                "codeartifact:ReadFromRepository",
                "codeartifact:GetRepositoryEndpoint",
            ],
            resources=["*"],
        )

        with open("lambda/lambda_handler.py", encoding="utf8") as fp:
            handler_code = fp.read()

        # Create Lambda
        lambda_fn = lambda_.Function(
            self,
            "MWAA-UpdateCodeArtifactIndexURL",
            code=lambda_.InlineCode(handler_code),
            handler="index.handler",
            timeout=cdk.Duration.seconds(300),
            runtime=lambda_.Runtime.PYTHON_3_12,
            environment={
                "CA_DOMAIN": ca.repo.domain_name,
                "CA_DOMAIN_OWNER": self.account,
                "CA_REPOSITORY_NAME": ca.repo.repository_name,
                "BUCKET_NAME": s3.instance.bucket_name,
            },
            initial_policy=[ca_token_policy, ca_sts_policy],
        )

        # Give permission to read/write from the S3 bucket
        s3.instance.grant_read_write(lambda_fn)

        # Run Lambda every 10 hours
        rule = events.Rule(
            self,
            "Rule",
            schedule=events.Schedule.rate(cdk.Duration.hours(10)),
            enabled=True,
        )
        rule.add_target(targets.LambdaFunction(lambda_fn))

        # Invoke Lambda once after cdk deploy
        cdk.CustomResource(self, "InvokeLambda", service_token=lambda_fn.function_arn)