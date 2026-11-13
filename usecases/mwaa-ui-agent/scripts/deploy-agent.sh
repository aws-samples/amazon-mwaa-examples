#!/usr/bin/env bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# Upload dist/agent.zip and deploy the AgentCore Runtime stack for one MWAA environment.
#
# Required environment variables:
#   MWAA_ENV_NAME       MWAA environment the agent serves
#   ARTIFACT_BUCKET     bucket for the agent package (versioning recommended)
# Optional:
#   ARTIFACT_BUCKET_OWNER  expected bucket-owner account ID (defaults to current caller account)
#   AWS_REGION          defaults to the environment's Region from your AWS config
#   STACK_NAME          defaults to mwaa-ui-agent-<env>
#   ATTACH_TO_EXECUTION_ROLE=true   add the invoke permission to the environment's execution role
#   ADDITIONAL_READ_BUCKET_ARNS     comma-separated bucket ARNs the agent may read (Glue/EMR scripts)
#   TEAM_DAG_FOLDERS=auto           multi-team (Airflow 3.3.1+) with ENABLE_DAG_AUTHORING: also allow writes
#                                   to every team's DAG folder from get-environment Teams
#   MODEL_ID            Bedrock model or inference profile ID
#   MODEL_REGION        Region for Bedrock calls (defaults to the stack Region)
#   ENABLED_SKILLS      comma-separated skills (default debugging-mwaa-workflow,testing-mwaa-workflow)
#   ENABLE_DAG_AUTHORING=true      let Op/Admin users deploy DAG files after approval (dev/test only);
#                                  grants s3:PutObject on the DAG folder and adds the authoring skill
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
: "${MWAA_ENV_NAME:?set MWAA_ENV_NAME}"
: "${ARTIFACT_BUCKET:?set ARTIFACT_BUCKET}"
REGION="${AWS_REGION:-$(aws configure get region)}"
export AWS_DEFAULT_REGION="$REGION"
STACK_NAME="${STACK_NAME:-mwaa-ui-agent-${MWAA_ENV_NAME}}"
ZIP="$ROOT/dist/agent.zip"
[[ -f "$ZIP" && ! -L "$ZIP" ]] || { echo "Build first (regular non-symlink file required): scripts/build-agent.sh" >&2; exit 1; }

env_json="$(aws mwaa get-environment --name "$MWAA_ENV_NAME" --output json)"
SOURCE_BUCKET="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["Environment"]["SourceBucketArn"].split(":::")[1])' <<<"$env_json")"
EXEC_ROLE_ARN="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["Environment"]["ExecutionRoleArn"])' <<<"$env_json")"
EXEC_ROLE_NAME="${EXEC_ROLE_ARN##*/}"
DAG_S3_PATH="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["Environment"].get("DagS3Path") or "dags")' <<<"$env_json")"
AIRFLOW_VERSION="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["Environment"]["AirflowVersion"])' <<<"$env_json")"

python3 - "$AIRFLOW_VERSION" <<'EOF'
import sys
major, minor = (int(x) for x in sys.argv[1].split(".")[:2])
if (major, minor) < (3, 1):
    sys.exit(f"Airflow {sys.argv[1]}: the plugin UI needs Airflow 3.1 or later")
EOF

HASH="$(shasum -a 256 "$ZIP" | cut -c1-16)"
KEY="mwaa-ui-agent/${MWAA_ENV_NAME}/agent-${HASH}.zip"
ARTIFACT_BUCKET_OWNER="${ARTIFACT_BUCKET_OWNER:-$(aws sts get-caller-identity --query Account --output text)}"
versioning="$(aws s3api get-bucket-versioning --bucket "$ARTIFACT_BUCKET" \
  --expected-bucket-owner "$ARTIFACT_BUCKET_OWNER" --query Status --output text)"
[[ "$versioning" == "Enabled" ]] || {
  echo "Artifact bucket versioning must be Enabled (got '$versioning')." >&2
  exit 1
}
upload_json="$(aws s3api put-object \
  --bucket "$ARTIFACT_BUCKET" \
  --key "$KEY" \
  --body "$ZIP" \
  --checksum-algorithm SHA256 \
  --expected-bucket-owner "$ARTIFACT_BUCKET_OWNER" \
  --output json)"
VERSION_ID="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("VersionId", ""))' <<<"$upload_json")"
CHECKSUM="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("ChecksumSHA256", ""))' <<<"$upload_json")"
[[ -n "$VERSION_ID" && -n "$CHECKSUM" ]] || {
  echo "Upload did not return both VersionId and ChecksumSHA256; refusing mutable artifact deployment." >&2
  exit 1
}

params=(
  "MwaaEnvironmentName=${MWAA_ENV_NAME}"
  "MwaaSourceBucketName=${SOURCE_BUCKET}"
  "ArtifactBucket=${ARTIFACT_BUCKET}"
  "ArtifactKey=${KEY}"
  "ArtifactVersionId=${VERSION_ID}"
)
[[ "${ATTACH_TO_EXECUTION_ROLE:-false}" == "true" ]] && params+=("MwaaExecutionRoleName=${EXEC_ROLE_NAME}")
[[ -n "${ADDITIONAL_READ_BUCKET_ARNS:-}" ]] && params+=("AdditionalReadOnlyBucketArns=${ADDITIONAL_READ_BUCKET_ARNS}")
[[ -n "${MODEL_ID:-}" ]] && params+=("ModelId=${MODEL_ID}")
[[ -n "${MODEL_REGION:-}" ]] && params+=("ModelRegion=${MODEL_REGION}")
if [[ "${ENABLE_DAG_AUTHORING:-false}" == "true" ]]; then
  params+=("EnableDagAuthoring=true" "MwaaDagS3Path=${DAG_S3_PATH%/}")
  if [[ "${TEAM_DAG_FOLDERS:-}" == "auto" ]]; then
    TEAM_ARNS="$(python3 -c '
import json, sys
teams = json.load(sys.stdin)["Environment"].get("Teams") or {}
print(",".join(
    t["SourceBucketArn"] + "/" + t["DagS3Path"].strip("/")
    for t in teams.values()
    if t.get("SourceBucketArn") and (t.get("DagS3Path") or "").strip("/")
))
' <<<"$env_json")"
    # A bare bucket ARN would let the agent write next to requirements.txt and the startup script.
    IFS=',' read -r -a team_arn_list <<<"$TEAM_ARNS"
    for arn in "${team_arn_list[@]}"; do
      [[ "$arn" =~ ^arn:aws[a-z-]*:s3:::[a-z0-9][a-z0-9.-]+/[A-Za-z0-9_./-]+$ ]] || {
        echo "Refusing team DAG folder '$arn': it must be arn:...:s3:::bucket/prefix" >&2; exit 1; }
    done
    [[ -n "$TEAM_ARNS" ]] && params+=("TeamDagFolders=${TEAM_ARNS}")
  fi
  ENABLED_SKILLS="${ENABLED_SKILLS:-debugging-mwaa-workflow,testing-mwaa-workflow,authoring-mwaa-workflow}"
else
  params+=("EnableDagAuthoring=false")
fi
[[ -n "${ENABLED_SKILLS:-}" ]] && params+=("EnabledSkills=${ENABLED_SKILLS// /}")

aws cloudformation deploy \
  --stack-name "$STACK_NAME" \
  --template-file "$ROOT/infra/agent-runtime.yaml" \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides "${params[@]}"

RUNTIME_ARN="$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='AgentRuntimeArn'].OutputValue" --output text)"

# update-environment replaces the whole option map, so merge the environment's existing options.
CONFIG_JSON="$(python3 -c '
import json, sys
opts = json.loads(sys.argv[1])["Environment"].get("AirflowConfigurationOptions") or {}
opts.update({"mwaa_agent.runtime_arn": sys.argv[2], "mwaa_agent.environment_name": sys.argv[3],
             "mwaa_agent.region": sys.argv[4]})
print(json.dumps(opts, sort_keys=True))
' "$env_json" "$RUNTIME_ARN" "$MWAA_ENV_NAME" "$REGION")"

cat <<EOF

Agent runtime: $RUNTIME_ARN

Next, upload dist/plugins.zip (merged with any existing plugins) outside the DAG folder, then configure
the plugin on the environment. This restarts the environment. The options below keep the existing ones.
  aws mwaa update-environment --name $MWAA_ENV_NAME \\
    --airflow-configuration-options '$CONFIG_JSON' \\
    --plugins-s3-path <key of plugins.zip> --plugins-s3-object-version <version of plugins.zip>
EOF
if [[ "${ATTACH_TO_EXECUTION_ROLE:-false}" != "true" ]]; then
  echo
  echo "The execution role $EXEC_ROLE_NAME still needs bedrock-agentcore:InvokeAgentRuntime on $RUNTIME_ARN and $RUNTIME_ARN/*."
fi
