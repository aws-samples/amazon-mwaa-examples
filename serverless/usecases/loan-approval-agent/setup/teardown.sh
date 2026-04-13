#!/usr/bin/env bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
set -euo pipefail

# ─── Configuration ───────────────────────────────────────────────
PROJECT="mwaa-loan-approval"
REGION="${1:-${AWS_REGION:-us-east-1}}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
S3_BUCKET="${PROJECT}-${ACCOUNT_ID}-${REGION}"
ROLE_NAME="${PROJECT}-role"
KB_ROLE_NAME="${PROJECT}-kb-role"
KB_NAME="${PROJECT}-salary-kb"
SNS_TOPIC_NAME="${PROJECT}-notifications"

echo "╔══════════════════════════════════════════════════════════╗"
echo "║       AI Loan Approval Agent — Teardown                 ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ─── 1. Delete MWAA Serverless Workflow ──────────────────────────
echo "▸ Deleting MWAA Serverless workflows..."
WORKFLOW_ARNS=$(aws mwaa-serverless list-workflows \
  --query "Workflows[?contains(WorkflowArn, 'loan_approval')].WorkflowArn" \
  --output text --region "${REGION}" 2>/dev/null || echo "")

for arn in ${WORKFLOW_ARNS}; do
  echo "  Deleting ${arn}..."
  aws mwaa-serverless delete-workflow --workflow-arn "${arn}" --region "${REGION}" 2>/dev/null || true
done
echo "  ✓ Workflows deleted."

# ─── 2. Delete Knowledge Base ────────────────────────────────────
echo "▸ Deleting Knowledge Base..."
KB_ID=$(aws bedrock-agent list-knowledge-bases \
  --query "knowledgeBaseSummaries[?name=='${KB_NAME}'].knowledgeBaseId | [0]" \
  --output text --region "${REGION}" 2>/dev/null || echo "None")

if [ "${KB_ID}" != "None" ] && [ -n "${KB_ID}" ]; then
  # Delete data sources first
  DS_IDS=$(aws bedrock-agent list-data-sources \
    --knowledge-base-id "${KB_ID}" \
    --query "dataSourceSummaries[].dataSourceId" \
    --output text --region "${REGION}" 2>/dev/null || echo "")
  for ds_id in ${DS_IDS}; do
    aws bedrock-agent delete-data-source \
      --knowledge-base-id "${KB_ID}" \
      --data-source-id "${ds_id}" \
      --region "${REGION}" 2>/dev/null || true
  done
  aws bedrock-agent delete-knowledge-base \
    --knowledge-base-id "${KB_ID}" \
    --region "${REGION}" 2>/dev/null || true
  echo "  ✓ Knowledge Base deleted."
else
  echo "  No Knowledge Base found."
fi

# ─── 3. Delete SNS Topic ────────────────────────────────────────
echo "▸ Deleting SNS topic..."
SNS_TOPIC_ARN="arn:aws:sns:${REGION}:${ACCOUNT_ID}:${SNS_TOPIC_NAME}"
aws sns delete-topic --topic-arn "${SNS_TOPIC_ARN}" --region "${REGION}" 2>/dev/null || true
echo "  ✓ SNS topic deleted."

# ─── 4. Delete IAM Roles ────────────────────────────────────────
echo "▸ Deleting IAM roles..."
for role in "${ROLE_NAME}" "${KB_ROLE_NAME}"; do
  POLICIES=$(aws iam list-role-policies --role-name "${role}" --query "PolicyNames" --output text 2>/dev/null || echo "")
  for policy in ${POLICIES}; do
    aws iam delete-role-policy --role-name "${role}" --policy-name "${policy}" 2>/dev/null || true
  done
  aws iam delete-role --role-name "${role}" 2>/dev/null || true
done
echo "  ✓ IAM roles deleted."

# ─── 5. Delete S3 Vector Bucket ──────────────────────────────────
echo "▸ Deleting S3 Vector Bucket..."
VECTOR_BUCKET_NAME="${PROJECT}-vectors"
VECTOR_INDEX_NAME="salary-embeddings"
aws s3vectors delete-index \
  --vector-bucket-name "${VECTOR_BUCKET_NAME}" \
  --index-name "${VECTOR_INDEX_NAME}" \
  --region "${REGION}" 2>/dev/null || true
aws s3vectors delete-vector-bucket \
  --vector-bucket-name "${VECTOR_BUCKET_NAME}" \
  --region "${REGION}" 2>/dev/null || true
echo "  ✓ Vector bucket deleted."

# ─── 6. Delete S3 Bucket ────────────────────────────────────────
echo "▸ Deleting S3 bucket..."
if aws s3api head-bucket --bucket "${S3_BUCKET}" 2>/dev/null; then
  # Delete all object versions (required for versioned buckets)
  aws s3api list-object-versions --bucket "${S3_BUCKET}" --region "${REGION}" --output json 2>/dev/null | \
  python3 -c "
import sys, json, subprocess
data = json.load(sys.stdin)
objects = []
for v in data.get('Versions', []):
    objects.append({'Key': v['Key'], 'VersionId': v['VersionId']})
for d in data.get('DeleteMarkers', []):
    objects.append({'Key': d['Key'], 'VersionId': d['VersionId']})
if objects:
    for i in range(0, len(objects), 1000):
        batch = objects[i:i+1000]
        subprocess.run(['aws', 's3api', 'delete-objects', '--bucket', '${S3_BUCKET}', '--delete', json.dumps({'Objects': batch, 'Quiet': True}), '--region', '${REGION}'], capture_output=True)
    print(f'  Deleted {len(objects)} object versions')
"
  aws s3api delete-bucket --bucket "${S3_BUCKET}" --region "${REGION}" 2>/dev/null || true
  echo "  ✓ S3 bucket deleted."
else
  echo "  No bucket found."
fi

echo ""
echo "✓ Teardown complete."
