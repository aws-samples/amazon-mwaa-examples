#!/usr/bin/env bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# Stop the local test stack. Pass --wipe to also delete the local Airflow database volume.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
args=(down)
[[ "${1:-}" == "--wipe" ]] && args+=(--volumes)
docker compose -f "$HERE/docker-compose.yaml" --env-file "$HERE/.env" "${args[@]}"
rm -f "$HERE/.env.aws"
