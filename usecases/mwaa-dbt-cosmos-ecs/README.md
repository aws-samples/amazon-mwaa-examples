# Cosmos dbt on AWS ECS — MWAA 3.0.6 Example

Runs a dbt project on ECS Fargate using [Astronomer Cosmos](https://github.com/astronomer/astronomer-cosmos)
with the `AWS_ECS` execution mode. Each dbt model runs as a separate ECS Fargate task,
reading and writing Parquet files on S3 via DuckDB. No external database is needed.

Everything is provisioned and torn down automatically by the DAG.

## Architecture

```
Airflow (MWAA)
  ├─ ensure_clean_state       — delete leftover CloudFormation stack
  ├─ create_infra_stack       — CloudFormation: ECR, CodeBuild, ECS, IAM
  ├─ wait_for_infra           — wait for stack creation
  ├─ build_docker_image       — CodeBuild: build dbt-duckdb image → ECR
  ├─ dbt_seed_to_s3           — ECS: dbt seed + export seeds as Parquet to S3
  ├─ dbt_ecs (Cosmos TaskGroup)
  │   ├─ stg_customers_run    — ECS: reads seed Parquet from S3, writes staging Parquet
  │   ├─ stg_orders_run       — ECS: reads seed Parquet from S3, writes staging Parquet
  │   └─ customer_orders_run  — ECS: reads staging Parquet from S3, writes final Parquet
  └─ delete_infra_stack       — CloudFormation: tear down everything
```

## What Gets Provisioned

The CloudFormation stack creates:
- **ECR Repository** — stores the dbt Docker image (auto-emptied on delete)
- **CodeBuild Project** — builds the image from `python:3.11-slim` + `dbt-duckdb`
- **ECS Cluster** — Fargate cluster for running dbt tasks
- **ECS Task Definition** — container config with CloudWatch logging
- **IAM Roles** — CodeBuild service role, ECS execution role, ECS task role (with S3 access)

Everything is deleted after the DAG completes (even on failure).

## S3 Output

The DAG writes all data as Parquet to `s3://<bucket>/dbt_output/`:

```
dbt_output/
├── seeds/
│   ├── raw_customers.parquet
│   └── raw_orders.parquet
├── stg_customers.parquet
├── stg_orders.parquet
└── customer_orders.parquet
```

These files can be queried directly by Athena, Redshift Spectrum, Spark, or any
Parquet-compatible tool.

## Directory Structure

```
dbt/
├── cosmos_dbt_ecs_dag.py           # Airflow DAG
├── README.md
└── dbt_project/
    ├── dbt_project.yml             # dbt config + on-run-start hooks for S3 auth
    ├── profiles.yml                # DuckDB profile with httpfs + aws extensions
    ├── entrypoint.sh               # Docker entrypoint: fetches ECS task role creds
    ├── macros/
    │   └── export_to_s3.sql        # Macro to export seed tables as Parquet to S3
    ├── models/
    │   ├── schema.yml
    │   ├── stg_customers.sql       # External materialization → S3 Parquet
    │   ├── stg_orders.sql          # External materialization → S3 Parquet
    │   └── customer_orders.sql     # External materialization → S3 Parquet
    └── seeds/
        ├── raw_customers.csv
        └── raw_orders.csv
```

## Prerequisites

- Amazon MWAA environment (Airflow 3.0.6) with `astronomer-cosmos[aws-ecs]==1.14.0` in requirements.txt
- MWAA execution role with permissions for: ECS, ECR, CodeBuild, CloudFormation,
  IAM (PassRole/CreateRole/AttachRolePolicy/DeleteRole), S3, CloudWatch Logs
- VPC must have public subnets (MapPublicIpOnLaunch=true) for ECS Fargate internet access

### MWAA Execution Role IAM Permissions

The MWAA execution role needs the following permissions beyond the default MWAA policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DAGParseTime",
      "Effect": "Allow",
      "Action": [
        "airflow:GetEnvironment",
        "ec2:DescribeSubnets"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CloudFormation",
      "Effect": "Allow",
      "Action": [
        "cloudformation:CreateStack",
        "cloudformation:DeleteStack",
        "cloudformation:DescribeStacks",
        "cloudformation:DescribeStackEvents"
      ],
      "Resource": "arn:aws:cloudformation:*:*:stack/cosmos-dbt-ecs-selfcontained/*"
    },
    {
      "Sid": "ECS",
      "Effect": "Allow",
      "Action": [
        "ecs:CreateCluster",
        "ecs:DeleteCluster",
        "ecs:RegisterTaskDefinition",
        "ecs:DeregisterTaskDefinition",
        "ecs:RunTask",
        "ecs:DescribeTasks",
        "ecs:StopTask"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ECR",
      "Effect": "Allow",
      "Action": [
        "ecr:CreateRepository",
        "ecr:DeleteRepository",
        "ecr:BatchDeleteImage",
        "ecr:BatchCheckLayerAvailability",
        "ecr:BatchGetImage",
        "ecr:GetDownloadUrlForLayer",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload",
        "ecr:GetAuthorizationToken"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CodeBuild",
      "Effect": "Allow",
      "Action": [
        "codebuild:CreateProject",
        "codebuild:DeleteProject",
        "codebuild:StartBuild",
        "codebuild:BatchGetBuilds"
      ],
      "Resource": "*"
    },
    {
      "Sid": "IAMForCloudFormation",
      "Effect": "Allow",
      "Action": [
        "iam:CreateRole",
        "iam:DeleteRole",
        "iam:GetRole",
        "iam:PassRole",
        "iam:AttachRolePolicy",
        "iam:DetachRolePolicy",
        "iam:PutRolePolicy",
        "iam:DeleteRolePolicy"
      ],
      "Resource": [
        "arn:aws:iam::*:role/cosmos-dbt-ecs-selfcontained-*"
      ]
    },
    {
      "Sid": "S3",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:GetBucketLocation", "s3:ListBucket"],
      "Resource": ["arn:aws:s3:::${MWAA_BUCKET}", "arn:aws:s3:::${MWAA_BUCKET}/*"]
    },
    {
      "Sid": "CloudWatchLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "logs:DeleteLogGroup",
        "logs:DescribeLogStreams",
        "logs:GetLogEvents"
      ],
      "Resource": "*"
    }
  ]
}
```

Replace `${MWAA_BUCKET}` with your MWAA environment's S3 source bucket name.

## Setup

1. Upload this folder to your MWAA S3 bucket under `dags/3.0/dbt/`
2. Ensure `astronomer-cosmos[aws-ecs]==1.14.0` is in your MWAA requirements.txt
3. The DAG will appear as `cosmos_dbt_ecs_dag` — trigger it manually

No hardcoded configuration is needed. The DAG automatically derives:
- **Region and Account ID** from `MWAA__LOGGING__AIRFLOW_TASK_LOG_GROUP_ARN`
- **S3 bucket** from the MWAA environment's source bucket
- **Subnets** by finding public subnets in the MWAA VPC
- **Security group** from the MWAA environment's network configuration

## How It Works

1. **Infrastructure provisioning**: CloudFormation creates all AWS resources
2. **Docker image build**: CodeBuild downloads the dbt project from S3 and builds a
   Docker image with dbt-duckdb installed. The image includes an entrypoint script
   that fetches ECS task role credentials from the container metadata endpoint.
3. **Seed loading**: A single ECS task runs `dbt seed` to load CSV data into DuckDB,
   then exports the seed tables as Parquet files to S3
4. **Model execution (Cosmos)**: Each dbt model runs as a separate ECS Fargate task
   via Cosmos `DbtTaskGroup` with `ExecutionMode.AWS_ECS`. Models use `external`
   materialization to read upstream Parquet from S3 and write output Parquet to S3.
   This allows each isolated container to participate in the dbt dependency graph.
5. **Cleanup**: CloudFormation deletes all provisioned resources

## Key Design Decisions

- **Zero hardcoded config**: region, account, subnets, security group, and S3 bucket
  are all derived at DAG parse time from MWAA environment variables and the
  `mwaa:GetEnvironment` / `ec2:DescribeSubnets` APIs
- **DuckDB + S3 Parquet** instead of a shared database: each ECS container is
  ephemeral, so models use `read_parquet('s3://...')` for upstream data and
  `external` materialization to write results back to S3
- **`entrypoint.sh`** fetches ECS task role credentials and exports them as
  environment variables, since DuckDB's `credential_chain` doesn't natively
  read the ECS container metadata endpoint
- **`on-run-start` hooks** install DuckDB's `httpfs` and `aws` extensions and
  create an S3 secret using `credential_chain` (which picks up the env vars
  set by the entrypoint)
- **`LoadMode.CUSTOM`** for Cosmos parsing: avoids needing dbt installed on the
  MWAA worker — Cosmos parses the SQL files directly
