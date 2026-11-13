#!/usr/bin/env bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# Build the AgentCore Runtime direct-code-deployment package: dist/agent.zip
# Dependencies are installed as Linux arm64 wheels, which is what AgentCore Runtime runs.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="$ROOT/build/agent"
DIST="$ROOT/dist"

rm -rf "$BUILD"
mkdir -p "$BUILD" "$DIST"

uv pip install \
  --quiet \
  --target "$BUILD" \
  --python-version 3.12 \
  --python-platform aarch64-manylinux2014 \
  --only-binary=:all: \
  --require-hashes \
  -r "$ROOT/agent/requirements.lock"

cp "$ROOT/agent/main.py" "$BUILD/"
cp -R "$ROOT/agent/mwaa_agent" "$BUILD/"
if find "$ROOT/agent" -path "$ROOT/agent/tests" -prune -o -type l -print -quit | grep -q .; then
  echo "Refusing symlinks in agent source" >&2
  exit 1
fi
"$ROOT/scripts/vendor-skills.sh" "$BUILD/skills"
if find "$BUILD" -type l -print -quit | grep -q .; then
  echo "Refusing symlinks in agent package" >&2
  exit 1
fi

find "$BUILD" -name '__pycache__' -type d -prune -exec rm -rf {} +
chmod -R u=rwX,go=rX "$BUILD"

rm -f "$DIST/agent.zip"
(cd "$BUILD" && zip -qr "$DIST/agent.zip" .)
echo "Built $DIST/agent.zip ($(du -h "$DIST/agent.zip" | cut -f1))"
