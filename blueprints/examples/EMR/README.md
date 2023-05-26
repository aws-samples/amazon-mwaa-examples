# EMR on EKS with MWAA

This example deploys the following resources

- Creates EMR Cluster and runs a spark job using a DAG


## Prerequisites:

Ensure that you have installed the following tools on your machine.

1. [aws cli](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html)
2. [Make](https://www.make.com/en)
3. [Amazon MWAA](https://aws.amazon.com/managed-workflows-for-apache-airflow/)
4. An S3 bucket for storing EMR data and scripts.


_Note: If you do not have running MWAA environment, deploy it from the root of the project using terraform or CDK.

## Get started

Clone the repository

Navigate into one of the example directories and run `make` by passing MWAA environment related arguments

```sh
cd blueprints/examples/EMR
make deploy mwaa_bucket={MWAA_BUCKET} mwaa_execution_role_name=m{MWAA_EXEC_ROLE} mwaa_env_name={MWAA_ENV_NAME} emr_data_bucket={EMR_DATA_BUCKET}
```

## clean up
```sh
cd blueprints/examples/EMR
make destroy mwaa_bucket={MWAA_BUCKET} mwaa_execution_role_name=m{MWAA_EXEC_ROLE} mwaa_env_name={MWAA_ENV_NAME} emr_data_bucket={EMR_DATA_BUCKET}
```

## Login to MWAA

Login to your Amazon MWAA environment. You should see a dag by the name 'emr_sample'

Unpause the DAG and Run it from console


## What does the makefile do?
1. Copies the DAG and spark script to the S3 buckets
2. Attaches AmazonS3FullAccess and AmazonEMRFullAccessPolicy_v2 access permissions to MWAA execution role
3. Creates a variable in MWAA for the data bucket

## Clean up
```sh
cd blueprints/examples/EMR
make undeploy mwaa_bucket={MWAA_BUCKET} mwaa_execution_role_name={MWAA_EXEC_ROLE} mwaa_env_name={MWAA_ENV_NAME} emr_data_bucket={EMR_DATA_BUCKET}
```
