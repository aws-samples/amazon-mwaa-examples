# EMR on EKS with MWAA

This example is a quick start for orchestrating EMR on EKS jobs with MWAA



## Prerequisites:

Ensure that you have installed the following tools on your machine.

1. [aws cli](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html)
2. [kubectl](https://Kubernetes.io/docs/tasks/tools/)
3. [terraform](https://learn.hashicorp.com/tutorials/terraform/install-cli)
4. [Amazon MWAA](https://aws.amazon.com/managed-workflows-for-apache-airflow/)


_Note: If you do not have running MWAA environment, deploy it from the root of the project using terraform or CDK.

## Deploy EKS Clusters with EMR on EKS feature

Clone the repository

```sh
git clone https://github.com/aws-samples/amazon-mwaa-examples.git
cd blueprints/examples/EMR_on_EKS
```

### Terraform
```sh
make terraform-deploy mwaa_bucket={MWAA_BUCKET} mwaa_execution_role_name=m{MWAA_EXEC_ROLE} mwaa_env_name={MWAA_ENV_NAME}
```

### CDK
update the vpc_id attribute in infra/cdk/cdk.json to match your vpc
```sh
export AWS_DEFAULT_REGION={region}
make cdk-deploy mwaa_bucket={MWAA_BUCKET} mwaa_execution_role_name=m{MWAA_EXEC_ROLE} mwaa_env_name={MWAA_ENV_NAME}
```

## Login to MWAA

Login to your Amazon MWAA environment. You should see a dag by the name 'emr_eks_weatherstation_job'

Unpause the DAG and Run it from console

## What does the makefile do?
1. Create the infrastructure
    - EKS cluster
    - EMR on EKS virtual cluster
    - IAM role for EMR on EKS cluster, IAM policy with permissions to interact with EMR on EKS virtual cluster that will be attached to MWAA execution role
    - S3 buckets for MWAA DAGs, Spark scripts and data
2. Attaches EMR on EKS access permissions to MWAA execution role
3. Copy DAGs and Scripts to S3 buckets
4. Update MWAA environment with Variables neeed for DAGs

## What's needed for MWAA to access EMR EKS cluster

- Needs permissions to query and run jobs. EMR on EKS job needs a [job execution role](https://docs.amazonaws.cn/en_us/emr/latest/EMR-on-EKS-DevelopmentGuide/creating-job-execution-role.html). MWAA execution role will need oass role perission on the EMR job role. See policy statement below.

```json
{
    "Statement": [
        {
            "Action": [
                "emr-containers:StartJobRun",
                "emr-containers:ListJobRuns",
                "emr-containers:DescribeJobRun",
                "emr-containers:CancelJobRun"
            ],
            "Effect": "Allow",
            "Resource": [
                "arn:aws:emr-containers:{region}:{account}:/virtualclusters/*/jobruns/*",
                "arn:aws:emr-containers:{region}:{account}:/*"
            ],
            "Sid": "emrcontainers"
        },
        {
            "Action": "iam:PassRole",
            "Effect": "Allow",
            "Resource": [
                "arn:aws:iam::{account}:role/{emr_job_role}",
            ],
            "Sid": "emrcontainerspassrole"
        }
    ],
    "Version": "2012-10-17"
}
```
## Cleanup

### Terraform
```sh
make terraform-undeploy mwaa_bucket={MWAA_BUCKET} mwaa_execution_role_name=m{MWAA_EXEC_ROLE} mwaa_env_name={MWAA_ENV_NAME}
```

### CDK
update the vpc_id attribute in infra/cdk/cdk.json to match your vpc
```sh
export AWS_DEFAULT_REGION={region}
make cdk-undeploy mwaa_bucket={MWAA_BUCKET} mwaa_execution_role_name=m{MWAA_EXEC_ROLE} mwaa_env_name={MWAA_ENV_NAME}
```
## Troubleshooting

