#!/usr/bin/env bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# Build dist/plugins.zip with the Airflow plugin at the root of the archive.
# If your environment already uses a plugins.zip, merge these files into it instead:
# MWAA loads exactly one plugins archive per environment.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIST="$ROOT/dist"
mkdir -p "$DIST"
rm -f "$DIST/plugins.zip"
(cd "$ROOT/plugin" && zip -qr "$DIST/plugins.zip" mwaa_agent_plugin.py mwaa_agent_ui -x '*/__pycache__/*' '*.pyc')
unzip -l "$DIST/plugins.zip"
