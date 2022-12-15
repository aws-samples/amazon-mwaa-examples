from aws_cdk import (
    aws_iam,
    aws_kms
)

from constructs import Construct
from .common import constants


def create_kms_key(
        scope: Construct,
        construct_id: str,
        region: str,
        account: str) -> aws_kms.Key:
    policy_document = create_kms_policy(region, account)

    key_suffix = 'Key'
    key = aws_kms.Key(
        scope,
        f"{construct_id}{key_suffix}",
        enable_key_rotation=True,
        policy=policy_document,
    )

    key.add_alias(f"alias/{constants.MWAA_ENV}{key_suffix}")

    return key


def create_kms_policy(region: str, account: str) -> aws_iam.PolicyDocument:
    return aws_iam.PolicyDocument(
        statements=[
            aws_iam.PolicyStatement(
                actions=[
                    "kms:Create*",
                    "kms:Describe*",
                    "kms:Enable*",
                    "kms:List*",
                    "kms:Put*",
                    "kms:Decrypt*",
                    "kms:Update*",
                    "kms:Revoke*",
                    "kms:Disable*",
                    "kms:Get*",
                    "kms:Delete*",
                    "kms:ScheduleKeyDeletion",
                    "kms:GenerateDataKey*",
                    "kms:CancelKeyDeletion"
                ],
                principals=[
                    aws_iam.AccountRootPrincipal()
                ],
                resources=['*']
            ),
            aws_iam.PolicyStatement(
                actions=[
                    "kms:Decrypt*",
                    "kms:Describe*",
                    "kms:GenerateDataKey*",
                    "kms:Encrypt*",
                    "kms:ReEncrypt*",
                    "kms:PutKeyPolicy"
                ],
                effect=aws_iam.Effect.ALLOW,
                resources=["*"],
                principals=[aws_iam.ServicePrincipal("logs.amazonaws.com")],
                conditions={"ArnLike": {"kms:EncryptionContext:aws:logs:arn": f"arn:aws:logs:{region}:{account}:*"}}
            )
        ]
    )
