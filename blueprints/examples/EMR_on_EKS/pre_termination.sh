#!/bin/bash


aws s3 rm s3://$1/dags/emr_eks_dag.py
mwaa_cli_json=$(aws mwaa create-cli-token --name $3)
CLI_TOKEN=$(echo $mwaa_cli_json | jq -r '.CliToken')
WEB_SERVER_HOSTNAME=$(echo $mwaa_cli_json | jq -r '.WebServerHostname')
CLIRESULTS=$(curl --request POST "https://$WEB_SERVER_HOSTNAME/aws_mwaa/cli"  --header "Authorization: Bearer $CLI_TOKEN"  --header "Content-Type: text/plain"  --data-raw "variables delete JOB_ROLE_ARN ")
CLIRESULTS=$(curl --request POST "https://$WEB_SERVER_HOSTNAME/aws_mwaa/cli"  --header "Authorization: Bearer $CLI_TOKEN"  --header "Content-Type: text/plain"  --data-raw "variables delete DATA_BUCKET ")
CLIRESULTS=$(curl --request POST "https://$WEB_SERVER_HOSTNAME/aws_mwaa/cli"  --header "Authorization: Bearer $CLI_TOKEN"  --header "Content-Type: text/plain"  --data-raw "variables delete EMR_VIRTUAL_CLUSTER_ID ")

emr_on_eks_data_bucket='None'
if [[ "$4" == CDK ]]  
then
	export CDK_DEFAULT_ACCOUNT=$(aws sts get-caller-identity --query 'Account' --output text) 
	export CDK_DEFAULT_REGION=$AWS_DEFAULT_REGION 
	cd ./infra/cdk
    outputs=$(aws cloudformation describe-stacks --stack-name emr-eks-cdk --query "Stacks[0].Outputs")
    emr_on_eks_data_bucket=$(echo $outputs | jq -rc '.[] | select(.OutputKey=="emroneksdatabucket") | .OutputValue')
    aws iam detach-role-policy --policy-arn $(echo $outputs | jq -rc '.[] | select(.OutputKey=="emroneksmwaaiampolicyarn") | .OutputValue') --role-name $2 
    aws s3 rm s3://$emr_on_eks_data_bucket/ --recursive
    cdk destroy
    cd ../../
else
    aws iam detach-role-policy --policy-arn $(terraform -chdir="./infra/terraform" output -raw emr_on_eks_mwaa_iam_policy_arn) --role-name $2 
    emr_on_eks_data_bucket=$(terraform -chdir="./infra/terraform" output -raw emr_on_eks_data_bucket)
    aws s3 rm s3://$emr_on_eks_data_bucket/ --recursive

fi
