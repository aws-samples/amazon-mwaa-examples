# Glue with MWAA

This example is a quick start for orchestrating AWS Glue crawler and AWS Glue Job with MWAA
The example uses [NOAA Climatology data](https://docs.opendata.aws/noaa-ghcn-pds/readme.html)

## Prerequisites:

Ensure that you have installed the following tools on your machine.

1. [aws cli](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html)
3. [terraform](https://learn.hashicorp.com/tutorials/terraform/install-cli)
4. [Amazon MWAA](https://aws.amazon.com/managed-workflows-for-apache-airflow/)


_Note: If you do not have running MWAA environment, deploy it from the root of the project using terraform or CDK.

## Deploy EKS Clusters with EMR on EKS feature

Clone the repository

```sh
git clone https://github.com/aws-samples/amazon-mwaa-examples.git

```

Navigate into one of the example directories and run `make` by passing MWAA environment related arguments

```sh
cd blueprints/examples/AWSGlue
make deploy mwaa_bucket={MWAA_BUCKET} mwaa_execution_role_name={MWAA_EXEC_ROLE} mwaa_env_name={MWAA_ENV_NAME}
```

## Login to MWAA

Login to your Amazon MWAA environment. You should see a dag by the name 'emr_eks_weatherstation_job'

Unpause the DAG and Run it from console

## What does the makefile do?
1. Create the infrastructure
    - IAM service role for AWS Glue, IAM policy with AWS Glue permissions that will be attached MWAA execution role
    - S3 buckets for Spark scripts and data
2. Attaches Glue(IAM policy) access permissions to MWAA execution role
3. Copy DAGs and Scripts to S3 buckets
4. Update MWAA environment with Variables neeeded for DAGs.

## What's needed for MWAA to access Glue cluster

- Needs permissions to create/run AWS Glue crawler and Job. 

```json
{
    "Statement": [
        {
            "Action": [
                "glue:CreateJob",
                "glue:ListCrawlers",
                "glue:ListJobs",
                "glue:CreateCrawler"
                "glue:GetCrawlerMetrics"
                "glue:GetCrawler",
                "glue:StartCrawler",
                "glue:UpdateCrawler"
                "glue:StartJobRun",
                "glue:GetJobRun",
                "glue:UpdateJob",
                "glue:GetJob"
           ],
            "Effect": "Allow",
            "Resource": "*",
            "Sid": "Glue"
        },
        {
            "Action": [
            "iam:PassRole",
            "iam:GetRole"
            ],
            "Effect": "Allow",
            "Resource": [
                "arn:aws:iam::{account}:role/{glue_service_role}",
            ],
            "Sid": "Gluepassrole"
        }
    ],
    "Version": "2012-10-17"
}
```

## Clean up
```sh
cd blueprints/examples/AWSGlue
make deploy mwaa_bucket={MWAA_BUCKET} mwaa_execution_role_name={MWAA_EXEC_ROLE} mwaa_env_name={MWAA_ENV_NAME}
```
- Login to AWS account and delete AWS Glue tables starting with `year_`, AWS Glue Crawler named `noaa-weather-station-data` and AWS Glue Job `noaa_weatherdata_transform`