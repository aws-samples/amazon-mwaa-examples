import boto3
import cfnresponse
import os


def cfn_response(func):
    def wrapper(event, context):
        # Log request for CustomResource invocation
        print(f"REQUEST RECEIVED:\n {event}")

        res = func(event, context)
        event = res["event"]

        if "RequestType" in event:
            if event["RequestType"] == "Delete":
                cfnresponse.send(event, context, cfnresponse.SUCCESS, {})
            if event["RequestType"] in ["Create", "Update"]:
                status = (
                    cfnresponse.SUCCESS
                    if res["statusCode"] == 200
                    else cfnresponse.FAILED
                )
                cfnresponse.send(event, context, status, res["body"])

    return wrapper


@cfn_response
def handler(event, context):
    ca_domain = os.environ.get("CA_DOMAIN")
    ca_domain_owner = os.environ.get("CA_DOMAIN_OWNER")
    ca_repo_name = os.environ.get("CA_REPOSITORY_NAME")
    bucket_name = os.environ.get("BUCKET_NAME")
    region = os.environ.get("AWS_REGION")

    try:
        ca_client = boto3.client("codeartifact")
        res = ca_client.get_authorization_token(
            domain=ca_domain, domainOwner=ca_domain_owner, durationSeconds=43200
        )
        token = res["authorizationToken"]

        s3_client = boto3.client("s3")
        ca_index_url = (
            f"--index-url https://aws:{token}@{ca_domain}-{ca_domain_owner}"
            f".d.codeartifact.{region}.amazonaws.com/pypi/{ca_repo_name}/simple/"
        )
        s3_client.put_object(
            Body=ca_index_url, Bucket=bucket_name, Key="dags/codeartifact.txt"
        )
    except Exception as e:
        return {"statusCode": 500, "event": event, "body": {"Error": str(e)}}

    return {
        "statusCode": 200,
        "event": event,
        "body": {"Success": "CodeArtifact auth token for MWAA has been updated."},
    }
