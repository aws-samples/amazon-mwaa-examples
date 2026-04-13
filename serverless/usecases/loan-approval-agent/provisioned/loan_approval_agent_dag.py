# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#
# AI Loan Approval Agent — MWAA Provisioned (Python DAG)
#
# This DAG implements the same agentic loan approval workflow as the
# MWAA Serverless YAML version, but as a standard Python DAG for use
# with provisioned Amazon MWAA environments.
#
# Before using this DAG, you must:
#   1. Run the setup/deploy.sh script to create the Knowledge Base and
#      supporting resources, OR create them manually.
#   2. Set the following Airflow Variables (Admin > Variables):
#      - loan_approval_knowledge_base_id : Your Bedrock Knowledge Base ID
#      - loan_approval_sns_topic_arn     : Your SNS topic ARN
#      - loan_approval_s3_bucket         : Your S3 bucket name
#
from datetime import datetime

from airflow import DAG
from airflow.models.param import Param
from airflow.providers.amazon.aws.operators.bedrock import (
    BedrockInvokeModelOperator,
    BedrockRaGOperator,
)
from airflow.providers.amazon.aws.operators.s3 import S3CreateObjectOperator
from airflow.providers.amazon.aws.operators.sns import SnsPublishOperator

INFERENCE_PROFILE = "us.anthropic.claude-sonnet-4-20250514-v1:0"
KNOWLEDGE_BASE_ID = "{{ var.value.loan_approval_knowledge_base_id }}"
SNS_TOPIC_ARN = "{{ var.value.loan_approval_sns_topic_arn }}"
S3_BUCKET = "{{ var.value.loan_approval_s3_bucket }}"

with DAG(
    dag_id="loan_approval_agent",
    schedule=None,
    start_date=datetime(2025, 1, 1),
    catchup=False,
    params={
        "applicant_name": Param("Jane Doe", type="string"),
        "occupation": Param("software_engineer", type="string"),
        "yearly_income": Param(95000, type="number"),
        "loan_amount": Param(350000, type="number"),
    },
    tags=["bedrock", "agentic-ai", "loan-approval"],
) as dag:

    # ── Agent 1: Due Diligence (parallel) ──
    due_diligence = BedrockInvokeModelOperator(
        task_id="due_diligence",
        model_id=INFERENCE_PROFILE,
        input_data={
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
            "messages": [
                {
                    "role": "user",
                    "content": """You are a loan underwriting analyst. Assess the risk for this application:

- Applicant: {{ params.applicant_name }}
- Occupation: {{ params.occupation }}
- Yearly Income: ${{ params.yearly_income }}
- Loan Amount Requested: ${{ params.loan_amount }}

Evaluate:
1. Debt-to-income ratio (assume standard monthly expenses for the occupation)
2. Loan-to-income ratio and whether it falls within acceptable limits
3. Any red flags based on the occupation and requested amount

Return a JSON object with keys: risk_score (1-10), risk_factors (array), recommendation (string)""",
                }
            ],
        },
    )

    # ── Agent 2: Income Verification via RAG (parallel) ──
    income_verification = BedrockRaGOperator(
        task_id="income_verification",
        source_type="KNOWLEDGE_BASE",
        model_arn=INFERENCE_PROFILE,
        knowledge_base_id=KNOWLEDGE_BASE_ID,
        input=(
            "Verify if a yearly income of ${{ params.yearly_income }} is plausible "
            "for someone working as a {{ params.occupation }}. "
            "Check the salary ranges and flag any concerns. "
            "Return a JSON object with keys: verified (boolean), confidence (high/medium/low), "
            "expected_range (string), notes (string)"
        ),
    )

    # ── Agent 3: Final Decision (waits for both) ──
    loan_decision = BedrockInvokeModelOperator(
        task_id="loan_decision",
        model_id=INFERENCE_PROFILE,
        input_data={
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
            "messages": [
                {
                    "role": "user",
                    "content": """You are a senior loan officer making a final decision.

Application:
- Applicant: {{ params.applicant_name }}
- Occupation: {{ params.occupation }}
- Income: ${{ params.yearly_income }}
- Loan Amount: ${{ params.loan_amount }}

Due Diligence Report:
{{ ti.xcom_pull(task_ids="due_diligence") }}

Income Verification Report:
{{ ti.xcom_pull(task_ids="income_verification") }}

Based on both reports, make a final decision.
Return a JSON object with keys:
decision (APPROVED/DENIED/MANUAL_REVIEW),
reasoning (string), conditions (array of strings, if any)""",
                }
            ],
        },
    )

    # ── Notify applicant ──
    notify_applicant = SnsPublishOperator(
        task_id="notify_applicant",
        target_arn=SNS_TOPIC_ARN,
        message=(
            "Loan Application Decision for {{ params.applicant_name }}: "
            "{{ ti.xcom_pull(task_ids='loan_decision') }}"
        ),
        subject="Loan Application Decision - {{ params.applicant_name }}",
    )

    # ── Audit log to S3 ──
    log_decision = S3CreateObjectOperator(
        task_id="log_decision",
        s3_bucket=S3_BUCKET,
        s3_key="audit/{{ ds }}/{{ params.applicant_name }}.json",
        data=(
            '{"applicant": "{{ params.applicant_name }}", '
            '"occupation": "{{ params.occupation }}", '
            '"income": {{ params.yearly_income }}, '
            '"loan_amount": {{ params.loan_amount }}, '
            '"decision": {{ ti.xcom_pull(task_ids="loan_decision") }}}'
        ),
        replace=True,
    )

    # ── Dependencies: fan-out → fan-in ──
    [due_diligence, income_verification] >> loan_decision >> [notify_applicant, log_decision]
