
.PHONY: all
deploy: ## terraform
	terraform -chdir="./infra/terraform" init 
	terraform -chdir="./infra/terraform" plan 
	terraform -chdir="./infra/terraform" apply 
	$(MAKE) post-provision

post-provision:
	chmod 700 ./post_provision.sh
	./post_provision.sh $(mwaa_bucket) $(mwaa_execution_role_name) $(mwaa_env_name)  

undeploy:
	chmod 700 ./pre_termination.sh
	./pre_termination.sh  $(mwaa_bucket) $(mwaa_execution_role_name)
	terraform -chdir="./infra/terraform" destroy




