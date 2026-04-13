#!/usr/bin/env bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
set -euo pipefail

# ─── Configuration ───────────────────────────────────────────────
PROJECT="mwaa-loan-approval"
REGION="${1:-${AWS_REGION:-us-east-1}}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
S3_BUCKET="${PROJECT}-${ACCOUNT_ID}-${REGION}"
VECTOR_BUCKET_NAME="${PROJECT}-vectors"
VECTOR_INDEX_NAME="salary-embeddings"
ROLE_NAME="${PROJECT}-role"
KB_ROLE_NAME="${PROJECT}-kb-role"
KB_NAME="${PROJECT}-salary-kb"
SNS_TOPIC_NAME="${PROJECT}-notifications"
WORKFLOW_NAME="loan_approval_agent"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EMBEDDING_MODEL_ARN="arn:aws:bedrock:${REGION}::foundation-model/amazon.titan-embed-text-v2:0"

# Select regional inference profile based on region
case "${REGION}" in
  eu-*) INFERENCE_PROFILE_PREFIX="eu" ;;
  ap-*) INFERENCE_PROFILE_PREFIX="ap" ;;
  us-*) INFERENCE_PROFILE_PREFIX="us" ;;
  sa-*) INFERENCE_PROFILE_PREFIX="sa" ;;
  ca-*) INFERENCE_PROFILE_PREFIX="ca" ;;
  af-*) INFERENCE_PROFILE_PREFIX="af" ;;
  *)    INFERENCE_PROFILE_PREFIX="us" ;;
esac
INFERENCE_PROFILE="${INFERENCE_PROFILE_PREFIX}.anthropic.claude-sonnet-4-20250514-v1:0"
INFERENCE_MODEL_ARN="arn:aws:bedrock:${REGION}::inference-profile/${INFERENCE_PROFILE}"

echo "╔══════════════════════════════════════════════════════════╗"
echo "║       AI Loan Approval Agent — MWAA Serverless          ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "Region:     ${REGION}"
echo "Account:    ${ACCOUNT_ID}"
echo "S3 Bucket:  ${S3_BUCKET}"
echo ""

# ─── 1. Create S3 Bucket ────────────────────────────────────────
echo "▸ Creating S3 bucket..."
if aws s3api head-bucket --bucket "${S3_BUCKET}" 2>/dev/null; then
  echo "  Bucket already exists, skipping."
else
  if [ "${REGION}" = "us-east-1" ]; then
    aws s3api create-bucket --bucket "${S3_BUCKET}" --region "${REGION}" --output text > /dev/null
  else
    aws s3api create-bucket --bucket "${S3_BUCKET}" --region "${REGION}" \
      --create-bucket-configuration LocationConstraint="${REGION}" --output text > /dev/null
  fi
  aws s3api put-public-access-block --bucket "${S3_BUCKET}" \
    --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
  aws s3api put-bucket-versioning --bucket "${S3_BUCKET}" \
    --versioning-configuration Status=Enabled
  echo "  ✓ Bucket created."
fi

# ─── 2. Upload salary data ──────────────────────────────────────
echo "▸ Uploading salary data..."
aws s3 sync "${SCRIPT_DIR}/salary-data/" "s3://${S3_BUCKET}/salary-data/" --quiet
echo "  ✓ Salary data uploaded."

# ─── 3. Create SNS Topic ────────────────────────────────────────
echo "▸ Creating SNS topic..."
SNS_TOPIC_ARN=$(aws sns create-topic --name "${SNS_TOPIC_NAME}" --query TopicArn --output text --region "${REGION}")
echo "  ✓ SNS topic: ${SNS_TOPIC_ARN}"

# ─── 4. Create S3 Vector Bucket & Index ─────────────────────────
echo "▸ Creating S3 Vector Bucket..."
aws s3vectors create-vector-bucket \
  --vector-bucket-name "${VECTOR_BUCKET_NAME}" \
  --region "${REGION}" > /dev/null 2>&1 || true
VECTOR_BUCKET_ARN=$(aws s3vectors list-vector-buckets --region "${REGION}" \
  --query "vectorBuckets[?vectorBucketName=='${VECTOR_BUCKET_NAME}'].vectorBucketArn | [0]" --output text)
echo "  ✓ Vector bucket: ${VECTOR_BUCKET_ARN}"

echo "▸ Creating Vector Index (dimension=1024 for Titan Embed v2)..."
aws s3vectors create-index \
  --vector-bucket-name "${VECTOR_BUCKET_NAME}" \
  --index-name "${VECTOR_INDEX_NAME}" \
  --data-type float32 \
  --dimension 1024 \
  --distance-metric cosine \
  --region "${REGION}" > /dev/null 2>&1 || true
VECTOR_INDEX_ARN=$(aws s3vectors list-indexes --vector-bucket-name "${VECTOR_BUCKET_NAME}" --region "${REGION}" \
  --query "indexes[?indexName=='${VECTOR_INDEX_NAME}'].indexArn | [0]" --output text)
echo "  ✓ Vector index: ${VECTOR_INDEX_ARN}"

# ─── 5. Create Knowledge Base IAM Role ──────────────────────────
echo "▸ Creating Knowledge Base IAM role..."
KB_TRUST_POLICY='{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "bedrock.amazonaws.com"},
    "Action": "sts:AssumeRole",
    "Condition": {
      "StringEquals": {"aws:SourceAccount": "'"${ACCOUNT_ID}"'"},
      "ArnLike": {"aws:SourceArn": "arn:aws:bedrock:'"${REGION}"':'"${ACCOUNT_ID}"':knowledge-base/*"}
    }
  }]
}'

if aws iam get-role --role-name "${KB_ROLE_NAME}" 2>/dev/null; then
  echo "  Role already exists, updating trust policy."
  aws iam update-assume-role-policy \
    --role-name "${KB_ROLE_NAME}" \
    --policy-document "${KB_TRUST_POLICY}"
  sleep 10
else
  aws iam create-role \
    --role-name "${KB_ROLE_NAME}" \
    --assume-role-policy-document "${KB_TRUST_POLICY}" \
    --output text > /dev/null
fi

aws iam put-role-policy \
  --role-name "${KB_ROLE_NAME}" \
  --policy-name "${KB_ROLE_NAME}-policy" \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": ["bedrock:InvokeModel"],
        "Resource": "'"${EMBEDDING_MODEL_ARN}"'"
      },
      {
        "Effect": "Allow",
        "Action": ["s3:GetObject", "s3:ListBucket"],
        "Resource": [
          "arn:aws:s3:::'"${S3_BUCKET}"'",
          "arn:aws:s3:::'"${S3_BUCKET}"'/salary-data/*"
        ]
      },
      {
        "Effect": "Allow",
        "Action": [
          "s3vectors:CreateIndex",
          "s3vectors:PutVectors",
          "s3vectors:DeleteVectors",
          "s3vectors:GetVectors",
          "s3vectors:ListVectors",
          "s3vectors:QueryVectors",
          "s3vectors:DescribeIndex",
          "s3vectors:ListIndexes",
          "s3vectors:DescribeVectorBucket",
          "s3vectors:ListVectorBuckets"
        ],
        "Resource": [
          "'"${VECTOR_BUCKET_ARN}"'",
          "'"${VECTOR_INDEX_ARN}"'"
        ]
      }
    ]
  }'

KB_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${KB_ROLE_NAME}"
echo "  ✓ KB role: ${KB_ROLE_ARN}"
echo "  Waiting for IAM role propagation..."
sleep 10

# ─── 6. Create Bedrock Knowledge Base ───────────────────────────
echo "▸ Creating Bedrock Knowledge Base..."

EXISTING_KB_ID=$(aws bedrock-agent list-knowledge-bases \
  --query "knowledgeBaseSummaries[?name=='${KB_NAME}'].knowledgeBaseId | [0]" \
  --output text --region "${REGION}" 2>/dev/null || echo "None")

if [ "${EXISTING_KB_ID}" != "None" ] && [ -n "${EXISTING_KB_ID}" ]; then
  KB_ID="${EXISTING_KB_ID}"
  echo "  Knowledge Base already exists: ${KB_ID}"
else
  KB_ID=$(aws bedrock-agent create-knowledge-base \
    --name "${KB_NAME}" \
    --description "Salary benchmark data for income verification in loan applications" \
    --role-arn "${KB_ROLE_ARN}" \
    --knowledge-base-configuration '{
      "type": "VECTOR",
      "vectorKnowledgeBaseConfiguration": {
        "embeddingModelArn": "'"${EMBEDDING_MODEL_ARN}"'"
      }
    }' \
    --storage-configuration '{
      "type": "S3_VECTORS",
      "s3VectorsConfiguration": {
        "vectorBucketArn": "'"${VECTOR_BUCKET_ARN}"'",
        "indexArn": "'"${VECTOR_INDEX_ARN}"'"
      }
    }' \
    --query "knowledgeBase.knowledgeBaseId" \
    --output text \
    --region "${REGION}")
  echo "  ✓ Knowledge Base created: ${KB_ID}"
fi

echo "  Waiting for Knowledge Base to become ACTIVE..."
for i in $(seq 1 30); do
  STATUS=$(aws bedrock-agent get-knowledge-base \
    --knowledge-base-id "${KB_ID}" \
    --query "knowledgeBase.status" \
    --output text --region "${REGION}")
  if [ "${STATUS}" = "ACTIVE" ]; then
    echo "  ✓ Knowledge Base is ACTIVE."
    break
  fi
  if [ "${STATUS}" = "FAILED" ]; then
    echo "  ✗ Knowledge Base creation FAILED."
    aws bedrock-agent get-knowledge-base --knowledge-base-id "${KB_ID}" --region "${REGION}"
    exit 1
  fi
  echo "    Status: ${STATUS} (attempt ${i}/30)..."
  sleep 10
done

# ─── 7. Create Data Source & Ingest ─────────────────────────────
echo "▸ Creating data source and ingesting salary data..."

EXISTING_DS_ID=$(aws bedrock-agent list-data-sources \
  --knowledge-base-id "${KB_ID}" \
  --query "dataSourceSummaries[0].dataSourceId" \
  --output text --region "${REGION}" 2>/dev/null || echo "None")

if [ "${EXISTING_DS_ID}" != "None" ] && [ -n "${EXISTING_DS_ID}" ]; then
  DS_ID="${EXISTING_DS_ID}"
  echo "  Data source already exists: ${DS_ID}"
else
  DS_ID=$(aws bedrock-agent create-data-source \
    --knowledge-base-id "${KB_ID}" \
    --name "salary-benchmarks" \
    --data-source-configuration '{
      "type": "S3",
      "s3Configuration": {
        "bucketArn": "arn:aws:s3:::'"${S3_BUCKET}"'",
        "inclusionPrefixes": ["salary-data/"]
      }
    }' \
    --query "dataSource.dataSourceId" \
    --output text \
    --region "${REGION}")
  echo "  ✓ Data source created: ${DS_ID}"
fi

echo "  Starting ingestion job..."
INGESTION_JOB_ID=$(aws bedrock-agent start-ingestion-job \
  --knowledge-base-id "${KB_ID}" \
  --data-source-id "${DS_ID}" \
  --query "ingestionJob.ingestionJobId" \
  --output text \
  --region "${REGION}")

echo "  Waiting for ingestion to complete..."
for i in $(seq 1 30); do
  ING_STATUS=$(aws bedrock-agent get-ingestion-job \
    --knowledge-base-id "${KB_ID}" \
    --data-source-id "${DS_ID}" \
    --ingestion-job-id "${INGESTION_JOB_ID}" \
    --query "ingestionJob.status" \
    --output text --region "${REGION}")
  if [ "${ING_STATUS}" = "COMPLETE" ]; then
    echo "  ✓ Ingestion complete."
    break
  elif [ "${ING_STATUS}" = "FAILED" ]; then
    echo "  ✗ Ingestion failed."
    aws bedrock-agent get-ingestion-job \
      --knowledge-base-id "${KB_ID}" \
      --data-source-id "${DS_ID}" \
      --ingestion-job-id "${INGESTION_JOB_ID}" \
      --region "${REGION}"
    exit 1
  fi
  echo "    Ingestion status: ${ING_STATUS} (attempt ${i}/30)..."
  sleep 10
done

# ─── 8. Create MWAA Serverless Execution Role ───────────────────
echo "▸ Creating MWAA Serverless execution role..."

if aws iam get-role --role-name "${ROLE_NAME}" 2>/dev/null; then
  echo "  Role already exists, updating policy."
else
  aws iam create-role \
    --role-name "${ROLE_NAME}" \
    --assume-role-policy-document file://"${SCRIPT_DIR}/trust-policy.json" \
    --output text > /dev/null
fi

ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"

aws iam put-role-policy \
  --role-name "${ROLE_NAME}" \
  --policy-name "${ROLE_NAME}-policy" \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Sid": "CloudWatchLogs",
        "Effect": "Allow",
        "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
        "Resource": "*"
      },
      {
        "Sid": "BedrockInvoke",
        "Effect": "Allow",
        "Action": ["bedrock:InvokeModel"],
        "Resource": [
          "arn:aws:bedrock:'"${REGION}"':'"${ACCOUNT_ID}"':inference-profile/'"${INFERENCE_PROFILE}"'",
          "arn:aws:bedrock:*::foundation-model/anthropic.claude-sonnet-4-20250514-v1:0"
        ]
      },
      {
        "Sid": "BedrockRAG",
        "Effect": "Allow",
        "Action": ["bedrock:Retrieve", "bedrock:RetrieveAndGenerate"],
        "Resource": "arn:aws:bedrock:'"${REGION}"':'"${ACCOUNT_ID}"':knowledge-base/'"${KB_ID}"'"
      },
      {
        "Sid": "SNSPublish",
        "Effect": "Allow",
        "Action": ["sns:Publish"],
        "Resource": "'"${SNS_TOPIC_ARN}"'"
      },
      {
        "Sid": "S3Access",
        "Effect": "Allow",
        "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
        "Resource": [
          "arn:aws:s3:::'"${S3_BUCKET}"'",
          "arn:aws:s3:::'"${S3_BUCKET}"'/*"
        ]
      }
    ]
  }'

echo "  ✓ Execution role: ${ROLE_ARN}"
sleep 10

# ─── 9. Render & Upload Workflow YAML ────────────────────────────
echo "▸ Rendering and uploading workflow..."

sed -e "s|\${KNOWLEDGE_BASE_ID}|${KB_ID}|g" \
    -e "s|\${SNS_TOPIC_ARN}|${SNS_TOPIC_ARN}|g" \
    -e "s|\${S3_BUCKET}|${S3_BUCKET}|g" \
    -e "s|\${INFERENCE_PROFILE}|${INFERENCE_PROFILE}|g" \
    "${SCRIPT_DIR}/../loan_approval_agent.yaml" > /tmp/loan_approval_agent.yaml

aws s3 cp /tmp/loan_approval_agent.yaml \
  "s3://${S3_BUCKET}/yaml/loan_approval_agent.yaml" --quiet
echo "  ✓ Workflow uploaded."

# ─── 10. Create MWAA Serverless Workflow ─────────────────────────
echo "▸ Creating MWAA Serverless workflow..."

WORKFLOW_ARN=$(aws mwaa-serverless create-workflow \
  --name "${WORKFLOW_NAME}" \
  --definition-s3-location "{\"Bucket\":\"${S3_BUCKET}\",\"ObjectKey\":\"yaml/loan_approval_agent.yaml\"}" \
  --role-arn "${ROLE_ARN}" \
  --region "${REGION}" \
  --query "WorkflowArn" \
  --output text 2>&1) || true

if echo "${WORKFLOW_ARN}" | grep -q "ConflictException\|already exists"; then
  echo "  Workflow already exists, updating..."
  WORKFLOW_ARN=$(aws mwaa-serverless list-workflows \
    --query "Workflows[?contains(WorkflowArn, '${WORKFLOW_NAME}')].WorkflowArn | [0]" \
    --output text --region "${REGION}")
  aws mwaa-serverless update-workflow \
    --workflow-arn "${WORKFLOW_ARN}" \
    --definition-s3-location "{\"Bucket\":\"${S3_BUCKET}\",\"ObjectKey\":\"yaml/loan_approval_agent.yaml\"}" \
    --role-arn "${ROLE_ARN}" \
    --region "${REGION}" > /dev/null
fi

echo "  ✓ Workflow ARN: ${WORKFLOW_ARN}"

# ─── Done ────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║                    Setup Complete!                       ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "Run a loan application:"
echo ""
echo "  aws mwaa-serverless start-workflow-run \\"
echo "    --workflow-arn ${WORKFLOW_ARN} \\"
echo "    --override-parameters '{\"applicant_name\":\"Jane Doe\",\"occupation\":\"software_engineer\",\"yearly_income\":95000,\"loan_amount\":350000}' \\"
echo "    --region ${REGION}"
echo ""
echo "Check status:"
echo ""
echo "  aws mwaa-serverless get-workflow-run \\"
echo "    --workflow-arn ${WORKFLOW_ARN} \\"
echo "    --run-id <RUN_ID> \\"
echo "    --region ${REGION}"
echo ""
