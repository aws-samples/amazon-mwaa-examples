#!/bin/bash

aws s3 cp dags/emr.py s3://$1/dags/
aws iam attach-role-policy --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess --role-name $2 
aws iam attach-role-policy --policy-arn arn:aws:iam::aws:policy/AmazonEMRFullAccessPolicy_v2 --role-name $2 
aws s3 cp spark/nyc_aggregations.py s3://$4/spark/emr/
mwaa_cli_json=$(aws mwaa create-cli-token --name $3)
CLI_TOKEN=$(echo $mwaa_cli_json | jq -r '.CliToken')
WEB_SERVER_HOSTNAME=$(echo $mwaa_cli_json | jq -r '.WebServerHostname')
CLIRESULTS=$(curl --request POST "https://$WEB_SERVER_HOSTNAME/aws_mwaa/cli"  --header "Authorization: Bearer $CLI_TOKEN"  --header "Content-Type: text/plain"  --data-raw "variables set EMR_DATA_BUCKET $4")


