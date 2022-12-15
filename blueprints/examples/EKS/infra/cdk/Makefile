.PHONY: diff list vpc s3 mwaa infra eks-role s3-deploy

diff:
	@cdk diff --profile=${AWS_PROFILE}

list:
	@cdk list --profile=${AWS_PROFILE}

eks-role:
	@cdk deploy mwaa-blueprint-v1-eks-deps --profile=${AWS_PROFILE}

s3-deploy:
	@cdk deploy mwaa-blueprint-v1-s3-deploy --profile=${AWS_PROFILE}

infra:
	@cdk deploy mwaa-blueprint-v1-infra-* --profile=${AWS_PROFILE}