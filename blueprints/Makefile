.PHONY: debug cdk-install-requirements cdk-setup-vpc cdk-deploy-infra cdk-deploy-to-bucket cdk-list-stacks cdk-setup-mwaa-env cdk-diff cdk-setup-eks-role

install-cdk-requirements: ## install the python dependencies needed to run cdk IaC commands
	@pip install -r infra/cdk/requirements.txt

cdk-list: ## list all the stacks. due to SDK dependencies, this fails if run prior to S3 bucket creation
	@$(MAKE) -C infra/cdk list

cdk-diff: ## list the local changes in cdk compared to the previously installed infrastructure
	@$(MAKE) -C infra/cdk diff

cdk-deploy-infra:
	@S3_FLAG=False $(MAKE) -C infra/cdk infra

cdk-deploy-to-bucket: ## setup VPC needed for the mwaa infrastructure using CDK
	@$(MAKE) -C infra/cdk s3-deploy

cdk-setup-eks-role: ## setup the infrastructure dependencies for EKS cluster (eg: IAM Role)
	@$(MAKE) -C infra/cdk eks-role

help:
	@grep -E '^[a-zA-Z_-]+:.*?#.*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'