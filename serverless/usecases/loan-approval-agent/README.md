# AI Loan Approval Agent — MWAA Serverless

An agentic AI workflow that processes loan applications using parallel AI agents for due diligence and income verification, then makes an automated approval decision.

Built entirely with [Amazon MWAA Serverless](https://docs.aws.amazon.com/mwaa/latest/mwaa-serverless-userguide/what-is-mwaa-serverless.html) — no custom code, no infrastructure to manage.

## Architecture

```
                    ┌─────────────────────────────┐
                    │     Loan Application         │
                    │  (name, income, occupation,  │
                    │       loan amount)           │
                    └──────────┬──────────────────┘
                               │
                 ┌─────────────┴─────────────┐
                 │                           │
                 ▼                           ▼
    ┌────────────────────┐     ┌────────────────────────┐
    │  Agent 1:          │     │  Agent 2:              │
    │  Due Diligence     │     │  Income Verification   │
    │  (BedrockInvoke)   │     │  (BedrockRaG)          │
    │                    │     │                        │
    │  • Risk scoring    │     │  • Salary benchmarks   │
    │  • Debt-to-income  │     │  • Industry ranges     │
    │  • Red flags       │     │  • Plausibility check  │
    └────────┬───────────┘     └───────────┬────────────┘
             │                             │
             └──────────┬──────────────────┘
                        ▼
           ┌────────────────────────┐
           │  Agent 3:              │
           │  Loan Decision         │
           │  (BedrockInvoke)       │
           │                        │
           │  APPROVED / DENIED /   │
           │  MANUAL_REVIEW         │
           └────────────┬───────────┘
                        │
              ┌─────────┴─────────┐
              ▼                   ▼
    ┌──────────────┐    ┌──────────────┐
    │ SNS Notify   │    │ S3 Audit Log │
    └──────────────┘    └──────────────┘
```

## What Makes It Agentic

| Capability | How It Works |
|---|---|
| **Perception** | Receives structured application data as workflow params |
| **Parallel Reasoning** | Two AI agents independently assess risk and verify income |
| **Decision Making** | A third agent synthesizes both reports into a final decision |
| **Action** | Notifies the applicant and logs the decision for audit |

## Operators Used

All from the [Amazon Provider Package](https://airflow.apache.org/docs/apache-airflow-providers-amazon/stable/index.html) (MWAA Serverless compatible):

- `BedrockInvokeModelOperator` — Due diligence risk assessment + final decision
- `BedrockRaGOperator` — Income verification against salary benchmark knowledge base
- `SnsPublishOperator` — Applicant notification
- `S3CreateObjectOperator` — Audit trail

## Prerequisites

- [AWS CLI](https://aws.amazon.com/cli/) v2.31.38+
- An AWS account with [Amazon Bedrock](https://aws.amazon.com/bedrock/) model access enabled for:
  - `anthropic.claude-sonnet-4-20250514-v1:0` (inference via `us.anthropic.claude-sonnet-4-20250514-v1:0` inference profile)
  - `amazon.titan-embed-text-v2:0` (embeddings for Knowledge Base)
- Sufficient IAM permissions to create S3 buckets, IAM roles, SNS topics, Bedrock Knowledge Bases, S3 Vector buckets, and MWAA Serverless workflows

## Quick Start

### 1. Deploy everything

```bash
chmod +x setup/deploy.sh
./setup/deploy.sh
```

This single script creates:
- S3 bucket with salary benchmark data
- S3 Vector bucket and index for embeddings
- Bedrock Knowledge Base with S3 Vectors storage
- SNS topic for notifications
- IAM roles for MWAA Serverless and Bedrock
- The MWAA Serverless workflow

The deploy script is idempotent — safe to re-run if interrupted.

### 2. Run a loan application

```bash
aws mwaa-serverless start-workflow-run \
  --workflow-arn <WORKFLOW_ARN from deploy output> \
  --override-parameters '{"applicant_name":"Jane Doe","occupation":"software_engineer","yearly_income":95000,"loan_amount":350000}' \
  --region us-east-1
```

### 3. Check the result

```bash
aws mwaa-serverless get-workflow-run \
  --workflow-arn <WORKFLOW_ARN> \
  --run-id <RUN_ID from step 2> \
  --region us-east-1
```

### 4. Try different scenarios

```bash
# High-risk: teacher requesting large loan
aws mwaa-serverless start-workflow-run \
  --workflow-arn <WORKFLOW_ARN> \
  --override-parameters '{"applicant_name":"Bob Smith","occupation":"teacher","yearly_income":52000,"loan_amount":500000}' \
  --region us-east-1

# Low-risk: senior engineer, modest loan
aws mwaa-serverless start-workflow-run \
  --workflow-arn <WORKFLOW_ARN> \
  --override-parameters '{"applicant_name":"Alice Chen","occupation":"software_engineer","yearly_income":180000,"loan_amount":200000}' \
  --region us-east-1

# Suspicious: nurse with inflated income
aws mwaa-serverless start-workflow-run \
  --workflow-arn <WORKFLOW_ARN> \
  --override-parameters '{"applicant_name":"Tom Wilson","occupation":"nurse","yearly_income":250000,"loan_amount":400000}' \
  --region us-east-1
```

## Clean Up

```bash
chmod +x setup/teardown.sh
./setup/teardown.sh
```

## Project Structure

```
loan-approval-agent/
├── README.md                  # This file
├── loan_approval_agent.yaml              # MWAA Serverless workflow definition
├── provisioned/
│   └── loan_approval_agent_dag.py  # Python DAG for MWAA Provisioned
└── setup/
    ├── deploy.sh              # One-command setup
    ├── teardown.sh            # One-command cleanup
    ├── trust-policy.json      # IAM trust policy
    └── salary-data/           # Synthetic data for Knowledge Base
        ├── accountant.txt
        ├── nurse.txt
        ├── sales_manager.txt
        ├── software_engineer.txt
        └── teacher.txt
```

## MWAA Serverless vs. Provisioned

This example includes two versions of the same workflow:

| | Serverless (`loan_approval_agent.yaml`) | Provisioned (`provisioned/loan_approval_agent_dag.py`) |
|---|---|---|
| **Format** | YAML (DAG Factory) | Python |
| **Deployment** | `deploy.sh` creates the workflow | Copy DAG to your MWAA environment's S3 DAGs folder |
| **Configuration** | Placeholders rendered by `deploy.sh` | Airflow Variables (`Admin > Variables`) |
| **Infrastructure** | Fully managed, no environment needed | Requires an existing MWAA environment |
| **Cost model** | Pay per task execution | Hourly rate for always-on environment |
| **Custom code** | Not supported | Full Python flexibility |

### Using the Provisioned DAG

1. Run `setup/deploy.sh` to create the Knowledge Base, S3 bucket, and SNS topic (or create them manually).
2. Set the following [Airflow Variables](https://airflow.apache.org/docs/apache-airflow/stable/howto/variable.html) in your MWAA environment:
   - `loan_approval_knowledge_base_id` — Your Bedrock Knowledge Base ID
   - `loan_approval_sns_topic_arn` — Your SNS topic ARN
   - `loan_approval_s3_bucket` — Your S3 bucket name
3. Copy `provisioned/loan_approval_agent_dag.py` to your MWAA environment's DAGs S3 folder.
4. Trigger the DAG from the Airflow UI with custom parameters.

## Cost

This demo uses pay-per-use services only:
- **MWAA Serverless**: Charged per task execution time
- **Bedrock**: Charged per input/output token
- **S3, SNS**: Negligible for demo usage
- **Bedrock Knowledge Base (S3 Vectors)**: Storage costs only

Run `teardown.sh` when done to avoid ongoing charges.

## Security

See [CONTRIBUTING](../../../CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the [LICENSE](../../../LICENSE) file.
