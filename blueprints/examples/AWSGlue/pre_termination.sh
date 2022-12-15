#!/bin/bash

glue_mwaa_iam_policy_arn=$(terraform -chdir="./infra/terraform" output -raw glue_mwaa_iam_policy_arn)
aws iam detach-role-policy --policy-arn $glue_mwaa_iam_policy_arn --role-name $2 

data_bucket=$(terraform -chdir="./infra/terraform" output -raw glue_data_bucket_name)
aws s3 rm s3://$1/dags/weatherdata_processing.py
aws s3 rm s3://$data_bucket/ --recursive

