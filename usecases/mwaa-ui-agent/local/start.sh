#!/usr/bin/env bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# Start the local test stack: MWAA local image + UI plugin + agent.
#
# Prerequisites: Docker, the MWAA local image built from
# https://github.com/aws/amazon-mwaa-docker-images (default tag
# amazon-mwaa-docker-images/airflow:3.3.1-base; override with MWAA_LOCAL_IMAGE),
# and AWS credentials with Amazon Bedrock access (used only by the agent container).
#
# Environment: AWS_REGION (default eu-west-1), MODEL_ID, LOCAL_UI_PORT (default 8080), AWS_PROFILE.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
IMAGE="${MWAA_LOCAL_IMAGE:-amazon-mwaa-docker-images/airflow:3.3.1-base}"
PORT="${LOCAL_UI_PORT:-8080}"
export AWS_REGION="${AWS_REGION:-eu-west-1}"

docker image inspect "$IMAGE" >/dev/null 2>&1 || {
  echo "Image $IMAGE not found. Build it from amazon-mwaa-docker-images (images/airflow/3.3.1/build.sh)." >&2
  exit 1
}

# Per-checkout secrets for the local stack. Not used anywhere else.
for secret_file in "$HERE/.env" "$HERE/.env.aws"; do
  [[ ! -L "$secret_file" ]] || { echo "Refusing symlink: $secret_file" >&2; exit 1; }
done
if [[ ! -f "$HERE/.env" ]]; then
  tmp_env="$(mktemp "$HERE/.env.XXXXXX")"
  trap 'rm -f "${tmp_env:-}" "${tmp_aws:-}"' EXIT
  chmod 600 "$tmp_env"
  python3 - > "$tmp_env" <<'EOF'
import base64, secrets
print(f"FERNET_KEY={base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()}")
print(f"WEBSERVER_SECRET={secrets.token_urlsafe(32)}")
print(f"LOCAL_DB_PASSWORD={secrets.token_urlsafe(24)}")
print(f"LOCAL_AIRFLOW_PASSWORD={secrets.token_urlsafe(16)}")
print(f"LOCAL_AGENT_TOKEN={secrets.token_urlsafe(48)}")
EOF
  mv "$tmp_env" "$HERE/.env"
  tmp_env=""
  echo "Created $HERE/.env"
fi
# Add the invocation secret to an older generated file without replacing existing secrets.
if ! grep -q '^LOCAL_AGENT_TOKEN=' "$HERE/.env"; then
  value="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
  printf 'LOCAL_AGENT_TOKEN=%s\n' "$value" >> "$HERE/.env"
fi
chmod 600 "$HERE/.env"

# Temporary, non-admin credentials for Bedrock calls. Refreshed on every start.
umask 077
tmp_aws="$(mktemp "$HERE/.env.aws.XXXXXX")"
chmod 600 "$tmp_aws"
aws configure export-credentials --format env-no-export > "$tmp_aws"
if ! grep -q '^AWS_SESSION_TOKEN=' "$tmp_aws"; then
  rm -f "$tmp_aws"
  echo "Refusing long-term AWS credentials. Use a short-lived, least-privilege profile with a session token." >&2
  exit 1
fi
caller_arn="$(aws sts get-caller-identity --query Arn --output text)"
if [[ "$caller_arn" =~ /Admin/ ]] && [[ "${ALLOW_ADMIN_PROFILE:-false}" != "true" ]]; then
  rm -f "$tmp_aws"
  echo "Refusing admin credentials for the local agent ($caller_arn). Assume a Bedrock-only role." >&2
  echo "For an isolated throwaway account only, set ALLOW_ADMIN_PROFILE=true explicitly." >&2
  exit 1
fi
mv "$tmp_aws" "$HERE/.env.aws"
tmp_aws=""
umask 022

# Skills for the agent image, and the packaged plugin exactly as MWAA would load it.
[[ -f "$ROOT/build/agent/skills/SOURCE" ]] || "$ROOT/scripts/vendor-skills.sh" "$ROOT/build/agent/skills"
"$ROOT/scripts/build-plugin.sh" >/dev/null
# Empty the folder in place instead of deleting it: running containers bind-mount this directory, and
# replacing it would leave them mounting the deleted folder (the plugin then 404s until a restart).
mkdir -p "$HERE/.plugins" && find "$HERE/.plugins" -mindepth 1 -delete
mkdir -p "$HERE/dags/authored"  # DAG files written by the agent (git-ignored)
# Seed editable demo DAGs into the agent's folder once; later edits (by you or the agent) are kept.
for seed in "$HERE"/seed-dags/*.py; do
  [[ -e "$HERE/dags/authored/$(basename "$seed")" ]] || cp "$seed" "$HERE/dags/authored/"
done
mkdir -p "$HERE/.logs"  # task logs shared by all Airflow containers (git-ignored)
unzip -q "$ROOT/dist/plugins.zip" -d "$HERE/.plugins"

docker compose -f "$HERE/docker-compose.yaml" --env-file "$HERE/.env" up -d --build
# Airflow loads plugin code only at startup; restart the UI so a rebuilt plugin takes effect on reruns.
docker compose -f "$HERE/docker-compose.yaml" --env-file "$HERE/.env" restart webserver >/dev/null

echo "Waiting for the Airflow UI on http://127.0.0.1:${PORT} ..."
for _ in $(seq 1 90); do
  if curl -fsS "http://127.0.0.1:${PORT}/api/v2/monitor/health" >/dev/null 2>&1; then
    echo
    echo "Airflow UI:  http://127.0.0.1:${PORT}   (any username and password signs in as admin)"
    echo "Agent:       Global AI Agent button, or Browse > AI Agent"
    echo "Logs:        docker compose -f $HERE/docker-compose.yaml logs -f webserver mwaa-agent"
    exit 0
  fi
  sleep 5
done
echo "The UI did not become healthy in time. Check: docker compose -f $HERE/docker-compose.yaml logs webserver" >&2
exit 1
