#!/bin/bash

aws s3 cp dags/emr_eks_dag.py s3://$1/dags/
## aws s3 cp requirements.txt s3://$(mwaa_bucket)/
emr_on_eks_role_arn="None"
emr_on_eks_data_bucket="None"
emr_cluster_id="None"
if [[ "$4" == CDK ]]  
then
	export CDK_DEFAULT_ACCOUNT=$(aws sts get-caller-identity --query 'Account' --output text) 
	export CDK_DEFAULT_REGION=$AWS_DEFAULT_REGION 
	cd ./infra/cdk
    pip3 install -r requirements.txt
    cdk bootstrap
    cdk deploy
    outputs=$(aws cloudformation describe-stacks --stack-name emr-eks-cdk --query "Stacks[0].Outputs")
    emr_on_eks_role_arn=$(echo $outputs | jq -rc '.[] | select(.OutputKey=="emroneksrolearn") | .OutputValue')
    emr_on_eks_data_bucket=$(echo $outputs | jq -rc '.[] | select(.OutputKey=="emroneksdatabucket") | .OutputValue')
    emr_cluster_id=$(echo $outputs | jq -rc '.[] | select(.OutputKey=="emrcontainersvirtualclusterid") | .OutputValue')
    aws iam attach-role-policy --policy-arn $(echo $outputs | jq -rc '.[] | select(.OutputKey=="emroneksmwaaiampolicyarn") | .OutputValue') --role-name $2 
    cd ../../
else
    aws iam attach-role-policy --policy-arn $(terraform -chdir="./infra/terraform" output -raw emr_on_eks_mwaa_iam_policy_arn) --role-name $2 
    emr_on_eks_role_arn=$(terraform -chdir="./infra/terraform" output -json emr_on_eks_role_arn | jq -r '.[0]')
    emr_on_eks_data_bucket=$(terraform -chdir="./infra/terraform" output -raw emr_on_eks_data_bucket)
    emr_cluster_id=$(terraform -chdir="./infra/terraform" output -raw emrcontainers_virtual_cluster_id)
fi
aws s3 cp spark/etl.py s3://$emr_on_eks_data_bucket/spark/emreks/
mwaa_cli_json=$(aws mwaa create-cli-token --name $3)
CLI_TOKEN=$(echo $mwaa_cli_json | jq -r '.CliToken')
WEB_SERVER_HOSTNAME=$(echo $mwaa_cli_json | jq -r '.WebServerHostname')
CLIRESULTS=$(curl --request POST "https://$WEB_SERVER_HOSTNAME/aws_mwaa/cli"  --header "Authorization: Bearer $CLI_TOKEN"  --header "Content-Type: text/plain"  --data-raw "variables set JOB_ROLE_ARN $emr_on_eks_role_arn")
CLIRESULTS=$(curl --request POST "https://$WEB_SERVER_HOSTNAME/aws_mwaa/cli"  --header "Authorization: Bearer $CLI_TOKEN"  --header "Content-Type: text/plain"  --data-raw "variables set DATA_BUCKET $emr_on_eks_data_bucket")
CLIRESULTS=$(curl --request POST "https://$WEB_SERVER_HOSTNAME/aws_mwaa/cli"  --header "Authorization: Bearer $CLI_TOKEN"  --header "Content-Type: text/plain"  --data-raw "variables set EMR_VIRTUAL_CLUSTER_ID $emr_cluster_id")


