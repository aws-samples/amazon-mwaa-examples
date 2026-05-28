## Disclaimer

AWS code samples are example code that demonstrates practical implementations of AWS services for specific use cases and scenarios.

These application solutions are not supported products in their own right, but educational examples to help our customers use our products for their applications. As our customer, any applications you integrate these examples into should be thoroughly tested, secured, and optimized according to your business's security standards & policies before deploying to production or handling production workloads.

# MWAA Data Pipeline Workshop

One-command deployment of a provisioned MWAA instance with DAG Factory installed. As part of this stack data pipeline with VPC, Redshift, Glue, and EMR Serverless.

## Quick Start

```bash
# 1. Install prerequisites
pip install aws-sam-cli

# 2. Deploy everything
python3 deploy.py

# 3. Wait ~25 minutes, then access Airflow UI

# 4. Cleanup when done
python3 cleanup.py
```

## What Gets Deployed

### Provisioned MWAA Instance
- **MWAA 3.0.6** environment running Apache Airflow
- **DAG Factory** pre-installed for YAML-based DAG definitions
- Small environment size (suitable for development/testing)

### Data Pipeline Examples
1. **Python DAG** (`dags/data_pipeline.py`) - Traditional Airflow DAG written in Python
2. **YAML DAG** (`yaml/example_data_pipeline.yaml`) - DAG Factory representation of the same pipeline

### Infrastructure Components
- VPC with public/private subnets, NAT gateways
- Redshift Serverless (8 RPU)
- S3 bucket with DAGs, scripts, sample data
- IAM roles for Glue, EMR, Redshift

## Deploying to MWAA Serverless

The YAML-based DAG can be deployed to MWAA Serverless using the following commands:

### 1. Convert Python DAG to YAML
```bash
dag-converter convert data_pipeline.py --output yaml/
```

### 2. Upload YAML to S3
```bash
aws s3 sync yaml/ s3://YOUR-BUCKET-NAME/yaml/
```

### 3. Create Serverless Workflow
```bash
aws mwaa-serverless create-workflow \
  --name example_data_pipeline \
  --definition-s3-location '{ "Bucket": "YOUR-BUCKET-NAME", "ObjectKey": "yaml/example_data_pipeline.yaml" }' \
  --role-arn arn:aws:iam::YOUR-ACCOUNT-ID:role/service-role/YOUR-MWAA-EXECUTION-ROLE \
  --region us-east-2
```

### 4. List Serverless Workflows
```bash
aws mwaa-serverless list-workflows --region us-east-2
```

> **Note:** Replace `YOUR-BUCKET-NAME`, `YOUR-ACCOUNT-ID`, and `YOUR-MWAA-EXECUTION-ROLE` with your actual AWS resource identifiers.

## Pipeline Flow

```
S3 Data → Glue Crawler → Glue Transform → EMR Aggregate → Redshift
```

## Files

- `template.yaml` - SAM/CloudFormation template
- `deploy.py` - Deployment script
- `cleanup.py` - Cleanup script
- `dags/` - Airflow DAGs
- `scripts/` - Glue and EMR scripts
- `requirements/` - Python dependencies