#!/bin/bash


data_bucket=$(terraform -chdir="./infra/terraform" output -raw glue_data_bucket_name)

aws s3 cp dags/weatherdata_processing.py s3://$1/dags/
aws s3 cp scripts/noaa_weatherdata_transform.py s3://$data_bucket/scripts/

### Attach Glue MWAA policy to MWAA execution role
glue_mwaa_iam_policy_arn=$(terraform -chdir="./infra/terraform" output -raw glue_mwaa_iam_policy_arn)
aws iam attach-role-policy --policy-arn $glue_mwaa_iam_policy_arn --role-name $2 


### Create MWAA env variables
glue_service_role_arn=$(terraform -chdir="./infra/terraform" output -raw glue_service_role_arn)
glue_service_role_name=$(terraform -chdir="./infra/terraform" output -raw glue_service_role_name)

mwaa_cli_json=$(aws mwaa create-cli-token --name $3)
CLI_TOKEN=$(echo $mwaa_cli_json | jq -r '.CliToken')
WEB_SERVER_HOSTNAME=$(echo $mwaa_cli_json | jq -r '.WebServerHostname')
CLIRESULTS=$(curl --request POST "https://$WEB_SERVER_HOSTNAME/aws_mwaa/cli"  --header "Authorization: Bearer $CLI_TOKEN"  --header "Content-Type: text/plain"  --data-raw "variables set GLUE_SERVICE_ROLE_ARN $glue_service_role_arn")
CLIRESULTS=$(curl --request POST "https://$WEB_SERVER_HOSTNAME/aws_mwaa/cli"  --header "Authorization: Bearer $CLI_TOKEN"  --header "Content-Type: text/plain"  --data-raw "variables set DATA_BUCKET $data_bucket")
CLIRESULTS=$(curl --request POST "https://$WEB_SERVER_HOSTNAME/aws_mwaa/cli"  --header "Authorization: Bearer $CLI_TOKEN"  --header "Content-Type: text/plain"  --data-raw "variables set GLUE_SERVICE_ROLE_NAME $glue_service_role_name")


