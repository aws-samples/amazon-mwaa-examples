# MWAA Data Pipeline Workshop

One-command deployment of a complete MWAA data pipeline with VPC, Redshift, Glue, and EMR Serverless.

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

- VPC with public/private subnets, NAT gateways
- MWAA 2.10.3 small environment
- Redshift Serverless (8 RPU)
- S3 bucket with DAGs, scripts, sample data
- IAM roles for Glue, EMR, Redshift
- Python data pipeline DAG example
- YAML data pipeline DAG example

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