#!/bin/bash

glue_mwaa_iam_policy_arn=$(terraform -chdir="./infra/terraform" output -raw glue_mwaa_iam_policy_arn)
mwaa_role_name=$(terraform -chdir="./infra/terraform" output -raw mwaa_role_name)
aws iam detach-role-policy --policy-arn $glue_mwaa_iam_policy_arn --role-name $mwaa_role_name 


data_bucket=$(terraform -chdir="./infra/terraform" output -raw glue_data_bucket_name)
mwaa_bucket=$(terraform -chdir="./infra/terraform" output -raw mwaa_bucket_name)
aws s3 rm s3://$mwaa_bucket/dags/weatherdata_processing.py
aws s3 rm s3://$data_bucket/ --recursive

