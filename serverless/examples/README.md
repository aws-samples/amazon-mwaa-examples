# MWAA Serverless Example DAGs

This directory contains 29 example MWAA Serverless DAGs — one for each supported AWS service. Every DAG is **self-contained**: it provisions its own resources via CloudFormation, runs the service operations, and cleans up afterward.

## Prerequisites

- AWS CLI configured with credentials
- An S3 bucket (same region, versioning enabled, block public access) to store YAML definitions
- An IAM execution role trusting `airflow-serverless.amazonaws.com`

> **Note:** Replace `amzn-s3-demo-bucket` with your S3 bucket name, `111122223333` with your AWS account ID, and `us-east-1` with your region throughout.

## Quick Start

1. **Upload a DAG to S3:**
   ```bash
   aws s3 cp s3_dag.yaml s3://amzn-s3-demo-bucket/workflows/s3_dag.yaml
   ```

2. **Create the execution role** (see [IAM Execution Role](#iam-execution-role) below).

3. **Create and run the workflow:**
   ```bash
   aws mwaa-serverless create-workflow \
     --name s3-dag \
     --definition-s3-location '{"Bucket": "amzn-s3-demo-bucket", "ObjectKey": "workflows/s3_dag.yaml"}' \
     --role-arn arn:aws:iam::111122223333:role/mwaa-serverless-execution-role \
     --region us-east-1

   aws mwaa-serverless start-workflow-run \
     --workflow-arn <workflow-arn-from-above> \
     --region us-east-1
   ```

4. **Monitor the run:**
   ```bash
   aws mwaa-serverless get-workflow --workflow-arn <workflow-arn> --region us-east-1
   ```

## DAG Examples

### Storage & Data

| DAG | File | Description |
|-----|------|-------------|
| S3 | `s3_dag.yaml` | Create bucket, write/read/list/delete objects, delete bucket |
| DynamoDB | `dynamodb_dag.yaml` | Create table via CFN, poll for a value with DynamoDBValueSensor |
| Glacier | `glacier_dag.yaml` | Create vault via CFN, initiate inventory job, wait for completion |
| OpenSearch Serverless | `opensearch_serverless_dag.yaml` | Create collection with security/network policies, wait for active state |

### Analytics & ETL

| DAG | File | Description |
|-----|------|-------------|
| Glue | `glue_dag.yaml` | Create S3 bucket + IAM role via CFN, upload PySpark script, run Glue 5.0 job |
| Athena | `athena_dag.yaml` | Create COVID-19 data lake via CFN, run 3 parallel Athena queries |
| EMR | `emr_dag.yaml` | Create service role + instance profile via CFN, launch EMR cluster, wait for termination |
| EMR Serverless | `emr_serverless_dag.yaml` | Create IAM role + S3 bucket via CFN, create/stop/delete EMR Serverless application |
| Redshift | `redshift_dag.yaml` | Create Redshift Serverless namespace/workgroup via CFN, run SQL query |
| Kinesis Analytics | `kinesis_analytics_dag.yaml` | Create IAM role via CFN, create/start/stop Flink application |

### Compute

| DAG | File | Description |
|-----|------|-------------|
| Lambda | `lambda_dag.yaml` | Create Lambda function + IAM role via CFN, invoke function |
| Batch | `batch_dag.yaml` | Create VPC, Fargate compute env, job queue, job definition via CFN, submit job |
| ECS | `ecs_dag.yaml` | Create VPC, ECS cluster, Fargate task definition via CFN, run task |
| EKS | `eks_dag.yaml` | Create VPC, subnets, IAM role via CFN, create/delete EKS cluster |
| EC2 | `ec2_dag.yaml` | Create EC2 instance via CFN, stop/start instance, verify state |

### AI/ML

| DAG | File | Description |
|-----|------|-------------|
| Bedrock | `bedrock_dag.yaml` | Invoke Amazon Nova Lite model with a prompt |
| SageMaker | `sagemaker_dag.yaml` | Create IAM role via CFN, run SageMaker processing job |
| Comprehend | `comprehend_dag.yaml` | Create S3 bucket + IAM role via CFN, upload test data, run PII detection |

### Integration & Messaging

| DAG | File | Description |
|-----|------|-------------|
| Step Functions | `step_functions_dag.yaml` | Create state machine via CFN, start execution, wait for completion |
| SNS | `sns_dag.yaml` | Create SNS topic via CFN, publish message |
| SQS | `sqs_dag.yaml` | Create SQS queue via CFN, publish message, wait for message with sensor |
| EventBridge | `eventbridge_dag.yaml` | Create event bus + rule via CFN, put events, disable rule, clean up |
| AppFlow | `appflow_dag.yaml` | Create S3 buckets + flow via CFN, run flow |

### Database & Migration

| DAG | File | Description |
|-----|------|-------------|
| RDS | `rds_dag.yaml` | Create RDS MySQL instance via CFN, create/wait/delete snapshot |
| Neptune | `neptune_dag.yaml` | Create Neptune cluster via CFN, stop/start cluster |
| DMS | `dms_dag.yaml` | Create DMS replication instance via CFN |

### Other Services

| DAG | File | Description |
|-----|------|-------------|
| CloudFormation | `cloudformation_dag.yaml` | Create/wait/delete a sample CloudFormation stack |
| DataSync | `datasync_dag.yaml` | Create S3 source/dest + DataSync task via CFN, run sync |
| QuickSight | `quicksight_dag.yaml` | Create data source + dataset via CFN, create/wait for SPICE ingestion |

## IAM Execution Role

### Trust Policy

All DAGs require an execution role that trusts the MWAA Serverless service:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "airflow-serverless.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

### Per-DAG Permissions

Each DAG requires different IAM permissions. The table below shows the minimum actions needed for each. All DAGs also require `logs:CreateLogStream`, `logs:PutLogEvents`, `iam:PassRole`, and `iam:GetRole`.

| DAG | Required Actions |
|-----|-----------------|
| `s3_dag.yaml` | `s3:*` |
| `glue_dag.yaml` | `cloudformation:*`, `glue:*`, `iam:*`, `s3:*` |
| `athena_dag.yaml` | `athena:*`, `cloudformation:*`, `glue:*`, `iam:*`, `s3:*` |
| `bedrock_dag.yaml` | `bedrock:*` |
| `lambda_dag.yaml` | `cloudformation:*`, `iam:*`, `lambda:*` |
| `emr_serverless_dag.yaml` | `cloudformation:*`, `ec2:*`, `elasticmapreduce:*`, `iam:*` |
| `batch_dag.yaml` | `batch:*`, `cloudformation:*`, `iam:*` |
| `step_functions_dag.yaml` | `cloudformation:*`, `iam:*`, `states:*` |
| `redshift_dag.yaml` | `cloudformation:*`, `iam:*`, `redshift-data:*`, `redshift-serverless:*` |
| `sns_dag.yaml` | `cloudformation:*`, `iam:*`, `sns:*` |
| `ecs_dag.yaml` | `cloudformation:*`, `ec2:*`, `ecs:*`, `iam:*` |
| `eks_dag.yaml` | `cloudformation:*`, `ec2:*`, `eks:*`, `iam:*` |
| `emr_dag.yaml` | `cloudformation:*`, `ec2:*`, `elasticmapreduce:*`, `iam:*` |
| `cloudformation_dag.yaml` | `cloudformation:*`, `iam:*` |
| `sagemaker_dag.yaml` | `cloudformation:*`, `iam:*`, `sagemaker:*` |
| `rds_dag.yaml` | `cloudformation:*`, `iam:*`, `rds:*` |
| `ec2_dag.yaml` | `cloudformation:*`, `ec2:*`, `iam:*` |
| `sqs_dag.yaml` | `cloudformation:*`, `iam:*`, `sqs:*` |
| `eventbridge_dag.yaml` | `cloudformation:*`, `events:*`, `iam:*` |
| `comprehend_dag.yaml` | `cloudformation:*`, `comprehend:*`, `iam:*`, `s3:*` |
| `dms_dag.yaml` | `cloudformation:*`, `iam:*` |
| `kinesis_analytics_dag.yaml` | `cloudformation:*`, `iam:*`, `kinesisanalytics:*` |
| `neptune_dag.yaml` | `cloudformation:*`, `iam:*`, `neptune-db:*`, `rds:*` |
| `glacier_dag.yaml` | `cloudformation:*`, `glacier:*`, `iam:*` |
| `datasync_dag.yaml` | `cloudformation:*`, `datasync:*`, `iam:*` |
| `appflow_dag.yaml` | `appflow:*`, `cloudformation:*`, `iam:*` |
| `quicksight_dag.yaml` | `cloudformation:*`, `iam:*`, `quicksight:*` |
| `dynamodb_dag.yaml` | `cloudformation:*`, `dynamodb:*`, `iam:*` |
| `opensearch_serverless_dag.yaml` | `aoss:*`, `cloudformation:*`, `iam:*` |

### Comprehensive Test Policy

To run **all** DAGs with a single role, use this permissive policy (scope down for production):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CloudWatchLogs",
      "Effect": "Allow",
      "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
      "Resource": "*"
    },
    {
      "Sid": "IAMAccess",
      "Effect": "Allow",
      "Action": ["iam:*"],
      "Resource": "*"
    },
    {
      "Sid": "AllServiceAccess",
      "Effect": "Allow",
      "Action": [
        "aoss:*", "appflow:*", "athena:*", "batch:*", "bedrock:*",
        "cloudformation:*", "comprehend:*", "datasync:*", "dms:*",
        "dynamodb:*", "ec2:*", "ecs:*", "eks:*", "elasticmapreduce:*",
        "events:*", "glacier:*", "glue:*", "kinesisanalytics:*",
        "lambda:*", "neptune-db:*", "quicksight:*", "rds:*",
        "redshift-data:*", "redshift-serverless:*", "s3:*",
        "sagemaker:*", "sns:*", "sqs:*", "states:*"
      ],
      "Resource": "*"
    }
  ]
}
```

## Cleanup

Each DAG includes cleanup tasks with `trigger_rule: all_done` that run regardless of success or failure. If a run is interrupted, you may need to manually delete leftover CloudFormation stacks:

```bash
# List any leftover stacks
aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE ROLLBACK_FAILED DELETE_FAILED \
  --query 'StackSummaries[?starts_with(StackName,`mwaa-test`)].{Name:StackName,Status:StackStatus}' \
  --output table --region us-east-1

# Delete a stuck stack
aws cloudformation delete-stack --stack-name <stack-name> --region us-east-1
```

## Multi-Service Composite DAGs

These examples combine multiple AWS services into a single DAG, demonstrating chaining, parallel fan-out, and multi-stage pipelines.

| DAG | File | Pattern | Services |
|-----|------|---------|----------|
| S3 + Bedrock | `combo_s3_bedrock.yaml` | 2-service chain | S3 → Bedrock |
| SNS + SQS | `combo_sns_sqs.yaml` | 2-service chain | SNS → SQS |
| Lambda + Step Functions | `combo_lambda_sfn.yaml` | 2-service chain | Lambda → Step Functions |
| CFN + EC2 + RDS | `combo_cfn_ec2_rds.yaml` | 3-service chain | CloudFormation → EC2 → RDS |
| S3 + Parallel AI | `combo_s3_parallel_ai.yaml` | Parallel fan-out | S3 → (Bedrock ∥ Comprehend) |
| S3 → Glue → Athena → SNS | `combo_s3_glue_athena_sns.yaml` | 4-service pipeline | S3 → Glue → Athena → SNS |

### How composite DAGs work

- Each service's tasks are **prefixed** (e.g., `s3_create_test_bucket`, `glue_create_glue_stack`) to avoid ID collisions
- **Parameters are namespaced** (e.g., `sns_stack_name`, `sqs_stack_name`) so each service's config is independent
- **Cross-service dependencies** wire the last work task of the upstream service to the first task of the downstream service
- Each service's **cleanup tasks** still run independently with `trigger_rule: all_done`
- **Parallel fan-out** is achieved by having multiple services depend on the same upstream prefix

### Composite DAG IAM permissions

Composite DAGs require the union of permissions for all included services. For example, `combo_s3_glue_athena_sns.yaml` needs: `s3:*`, `glue:*`, `athena:*`, `sns:*`, `cloudformation:*`, `iam:*`.

Use the [Comprehensive Test Policy](#comprehensive-test-policy) to run all composite DAGs.

## Security

- These examples use permissive `*` resource policies for simplicity. For production, scope down to specific resource ARNs.
- CloudFormation templates create IAM roles with least-privilege policies for the services they support.
- All cleanup tasks use `trigger_rule: all_done` to prevent resource leaks on failure.

## License

This library is licensed under the MIT-0 License. See the [LICENSE](../../../LICENSE) file.
