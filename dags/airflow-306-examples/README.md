# Airflow 3.0.6 Examples for Amazon MWAA

This directory contains example Apache Airflow 3.0.6 DAGs demonstrating integration with various AWS services. These examples are designed to work with Amazon Managed Workflows for Apache Airflow (MWAA) and showcase best practices for workflow orchestration.

## Overview

These DAGs demonstrate how to use Airflow 3.0.6 with AWS services, including proper IAM permissions, error handling, and resource management. Each DAG is self-contained and includes inline documentation.

## Prerequisites

- Amazon MWAA environment (version 3.0.6 or later)
- AWS CLI configured with appropriate permissions
- IAM roles with required permissions (see [IAM Policy](#iam-policy))

## DAG Examples

### S3 Operations (`s3_airflow3_dag.py`)
Demonstrates S3 bucket and object operations including:
- Creating and deleting S3 buckets
- Creating, listing, and deleting S3 objects
- Using S3KeySensor to wait for objects

### Lambda Functions (`lambda_airflow3_dag.py`)
Shows Lambda function lifecycle management:
- Creating Lambda functions with inline code
- Waiting for function activation
- Invoking functions with payloads
- Self-cleanup functionality

### AWS Glue Jobs (`glue_airflow3_dag.py`)
Illustrates Glue ETL job execution:
- Creating and uploading Glue scripts to S3
- Running Glue 5.0 jobs with Python
- Monitoring job completion with sensors

### Amazon Athena (`athena_airflow3_dag.py`)
Demonstrates Athena query execution:
- Running SQL queries against data lakes
- Managing query results and outputs
- Integration with CloudFormation for resource creation

### AWS Batch (`batch_airflow3_dag.py`)
Shows containerized job execution:
- Creating Batch compute environments and job queues
- Submitting and monitoring Batch jobs
- Using Fargate for serverless compute

### EMR Serverless (`emr_serverless_airflow3_dag.py`)
Illustrates big data processing:
- Creating EMR Serverless applications
- Submitting Spark jobs
- Managing application lifecycle

### SageMaker Processing (`sagemaker_processing_airflow3_dag.py`)
Demonstrates ML data processing:
- Creating SageMaker processing jobs
- Using scikit-learn containers
- Processing data with automatic scaling

## Setup

1. **Upload DAG files to your MWAA S3 bucket:**
   ```bash
   aws s3 cp . s3://amzn-s3-demo-bucket/dags/ --recursive --exclude "*.md" --exclude "*.json"
   ```

2. **Create the required IAM execution role:**
   ```bash
   aws iam create-role \
     --role-name mwaa-airflow3-execution-role \
     --assume-role-policy-document file://trust-policy.json
   
   aws iam put-role-policy \
     --role-name mwaa-airflow3-execution-role \
     --policy-name mwaa-airflow3-policy \
     --policy-document file://mwaa-comprehensive-policy.json
   ```

3. **Update your MWAA environment configuration** to use the new execution role.

## IAM Policy

The comprehensive IAM policy required for all DAGs includes permissions for:

- S3 operations (bucket and object management)
- Lambda function lifecycle management
- Glue job creation and execution
- Athena query execution
- Batch job submission and monitoring
- EMR Serverless application management
- SageMaker processing jobs
- CloudFormation stack operations
- CloudWatch logging

```json
{
	"Version": "2012-10-17",
	"Statement": [
		{
			"Sid": "S3Permissions",
			"Effect": "Allow",
			"Action": [
				"s3:CreateBucket",
				"s3:DeleteBucket",
				"s3:ListBucket",
				"s3:GetObject",
				"s3:PutObject",
				"s3:DeleteObject"
			],
			"Resource": [
				"arn:aws:s3:::*",
				"arn:aws:s3:::*/*"
			]
		},
		{
			"Sid": "LambdaPermissions",
			"Effect": "Allow",
			"Action": [
				"lambda:CreateFunction",
				"lambda:DeleteFunction",
				"lambda:GetFunction",
				"lambda:InvokeFunction"
			],
			"Resource": "*"
		},
		{
			"Sid": "GluePermissions",
			"Effect": "Allow",
			"Action": [
				"glue:CreateJob",
				"glue:GetJob",
				"glue:StartJobRun",
				"glue:GetJobRun",
				"glue:GetTable",
				"glue:CreateTable",
				"glue:DeleteTable",
				"glue:CreateDatabase",
				"glue:DeleteDatabase"
			],
			"Resource": "*"
		},
		{
			"Sid": "AthenaPermissions",
			"Effect": "Allow",
			"Action": [
				"athena:StartQueryExecution",
				"athena:GetQueryExecution",
				"athena:GetQueryResults"
			],
			"Resource": "*"
		},
		{
			"Sid": "BatchPermissions",
			"Effect": "Allow",
			"Action": [
				"batch:SubmitJob",
				"batch:DescribeJobs",
				"batch:CreateJobQueue",
				"batch:DeleteJobQueue",
				"batch:UpdateJobQueue",
				"batch:RegisterJobDefinition",
				"batch:DeregisterJobDefinition",
				"batch:CreateComputeEnvironment",
				"batch:UpdateComputeEnvironment",
				"batch:DeleteComputeEnvironment",
				"batch:DescribeJobQueues",
				"batch:DescribeJobDefinitions",
				"batch:DescribeComputeEnvironments",
				"batch:TagResource"
			],
			"Resource": "*"
		},
		{
			"Sid": "CloudwatchPermissions",
			"Effect": "Allow",
			"Action": [
				"logs:CreateLogGroup",
				"logs:CreateLogStream",
				"logs:PutLogEvents"
			],
			"Resource": "*"
		},
		{
			"Sid": "EMRServerlessPermissions",
			"Effect": "Allow",
			"Action": [
				"emr-serverless:StartJobRun",
				"emr-serverless:GetJobRun",
				"emr-serverless:CreateApplication",
				"emr-serverless:GetApplication",
				"emr-serverless:StartApplication",
				"emr-serverless:DeleteApplication",
				"emr-serverless:ListJobRuns",
				"emr-serverless:StopApplication"
			],
			"Resource": "*"
		},
		{
			"Sid": "SageMakerPermissions",
			"Effect": "Allow",
			"Action": [
				"sagemaker:CreateProcessingJob",
				"sagemaker:DescribeProcessingJob"
			],
			"Resource": "*"
		},
		{
			"Sid": "CloudFormationPermissions",
			"Effect": "Allow",
			"Action": [
				"cloudformation:CreateStack",
				"cloudformation:DeleteStack",
				"cloudformation:DescribeStacks"
			],
			"Resource": "*"
		},
		{
			"Sid": "ECRPermissions",
			"Effect": "Allow",
			"Action": [
				"ecr:GetAuthorizationToken",
				"ecr:BatchCheckLayerAvailability",
				"ecr:GetDownloadUrlForLayer",
				"ecr:BatchGetImage"
			],
			"Resource": "*"
		},
		{
			"Sid": "ECSPermissions",
			"Effect": "Allow",
			"Action": [
				"ecs:DescribeTaskDefinition"
			],
			"Resource": "*"
		},
		{
			"Sid": "CloudWatchLogsPermissions",
			"Effect": "Allow",
			"Action": [
				"logs:CreateLogGroup",
				"logs:CreateLogStream",
				"logs:PutLogEvents"
			],
			"Resource": "*"
		},
		{
			"Sid": "IAMPassRolePermissions",
			"Effect": "Allow",
			"Action": [
				"iam:PassRole",
				"iam:GetRole"
			],
			"Resource": "*"
		}
	]
}
```

### Trust Relationships

Your execution role needs trust relationships for:


**Service Roles (for PassRole operations):**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": [
          "airflow.amazonaws.com",
          "airflow-env.amazonaws.com",
          "lambda.amazonaws.com",
          "glue.amazonaws.com",
          "sagemaker.amazonaws.com",
          "batch.amazonaws.com",
          "emr-serverless.amazonaws.com",
          "ecs-tasks.amazonaws.com"
        ]
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

## Usage

1. **Enable DAGs** in the Airflow UI
2. **Configure parameters** as needed for your environment
3. **Trigger DAGs** manually or via schedule
4. **Monitor execution** through CloudWatch logs

## Configuration

Most DAGs use parameters that can be customized:

- `role_arn`: IAM role for service operations
- `s3_bucket`: S3 bucket for data and scripts
- `region`: AWS region for resources

Update these parameters in the Airflow UI or via environment variables.

## Troubleshooting

### Common Issues

- **IAM Permission Errors**: Ensure your execution role has all required permissions
- **Resource Not Found**: Verify S3 buckets and objects exist before running DAGs
- **Timeout Issues**: Adjust timeout values for long-running jobs

### Logs

Check CloudWatch logs for detailed error information:
- Airflow task logs: `/aws/amazonmwaa/[environment-name]/task`
- Service-specific logs: `/aws/glue/`, `/aws/batch/`, etc.

## Clean Up

Each DAG includes cleanup tasks where appropriate. For manual cleanup:

```bash
# Remove uploaded files
aws s3 rm s3://amzn-s3-demo-bucket/dags/ --recursive

# Delete IAM role and policies
aws iam delete-role-policy --role-name mwaa-airflow3-execution-role --policy-name mwaa-airflow3-policy
aws iam delete-role --role-name mwaa-airflow3-execution-role
```

## Security

- Always use least-privilege IAM permissions
- Sensitive data should be stored in AWS Secrets Manager
- Network access is controlled through VPC configuration

## Contributing

See [CONTRIBUTING](../../../CONTRIBUTING.md) for guidelines on contributing to this repository.

## License

This library is licensed under the MIT-0 License. See the [LICENSE](../../../LICENSE) file.
