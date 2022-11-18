
.PHONY: all
deploy: ## terraform
	terraform -chdir="./infra/terraform" init 
	terraform -chdir="./infra/terraform" plan 
	terraform -chdir="./infra/terraform" apply 
	$(MAKE) post-provision

post-provision:
	chmod 700 ./post_provision.sh
	./post_provision.sh MWAA_Metric_Environment 

undeploy:
	chmod 700 ./pre_termination.sh
	./pre_termination.sh  MWAA_Metric_Environment
	terraform -chdir="./infra/terraform" destroy




