

deploy:
	chmod 700 ./post_provision.sh
	./post_provision.sh $(mwaa_bucket) $(mwaa_execution_role_name) $(mwaa_env_name) $(emr_data_bucket)

undeploy:
	chmod 700 ./pre_termination.sh
	./pre_termination.sh  $(mwaa_bucket) $(mwaa_execution_role_name) $(mwaa_env_name) $(emr_data_bucket)
