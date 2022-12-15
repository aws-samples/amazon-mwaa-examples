.PHONY: all
terraform-deploy: ## terraform
	terraform -chdir="./infra/terraform" init 
	terraform -chdir="./infra/terraform" plan -out=terraform.out
	terraform -chdir="./infra/terraform" apply terraform.out
	$(MAKE) post-provision
cdk-deploy:
	chmod 700 ./post_provision.sh
	./post_provision.sh $(mwaa_bucket) $(mwaa_execution_role_name) $(mwaa_env_name) CDK

post-provision:
	chmod 700 ./post_provision.sh
	./post_provision.sh $(mwaa_bucket) $(mwaa_execution_role_name) $(mwaa_env_name) terraform

terraform-undeploy:
	chmod 700 ./pre_termination.sh
	./pre_termination.sh  $(mwaa_bucket) $(mwaa_execution_role_name) $(mwaa_env_name) terraform
	terraform -chdir="./infra/terraform" destroy

cdk-undeploy:
	chmod 700 ./pre_termination.sh
	./pre_termination.sh  $(mwaa_bucket) $(mwaa_execution_role_name) $(mwaa_env_name) CDK



