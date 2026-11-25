#!/usr/bin/env bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# Copy the MWAA skills from a strictly parsed, commit-pinned toolkit source.
set -euo pipefail
set -f

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${1:?usage: vendor-skills.sh <destination-dir>}"
LOCK="$ROOT/skills.lock"

read_json() { python3 -c 'import json,sys; v=json.load(open(sys.argv[1])); print(v[sys.argv[2]])' "$LOCK" "$1"; }
TOOLKIT_REPO="$(read_json toolkit_repo)"
TOOLKIT_REF="$(read_json toolkit_ref)"
SKILLS_PATH="$(read_json skills_path)"

[[ "$TOOLKIT_REPO" == "https://github.com/aws/agent-toolkit-for-aws.git" ]] || { echo "unapproved toolkit_repo" >&2; exit 1; }
[[ "$TOOLKIT_REF" =~ ^[0-9a-f]{40}$ ]] || { echo "toolkit_ref must be a full commit SHA" >&2; exit 1; }
[[ "$SKILLS_PATH" =~ ^[A-Za-z0-9._/-]+$ && "$SKILLS_PATH" != *..* && "$SKILLS_PATH" != /* ]] || {
  echo "invalid skills_path" >&2; exit 1;
}
[[ ! -L "$DEST" ]] || { echo "refusing symlink destination: $DEST" >&2; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

git -C "$TMP" init -q
git -C "$TMP" remote add origin "$TOOLKIT_REPO"
git -C "$TMP" sparse-checkout set --no-cone "/$SKILLS_PATH/"
git -C "$TMP" fetch -q --depth 1 --filter=blob:none origin "$TOOLKIT_REF"
git -C "$TMP" checkout -q FETCH_HEAD

mkdir -p "$DEST"
while IFS= read -r skill; do
  [[ "$skill" =~ ^[a-z0-9-]+$ ]] || { echo "invalid skill name: $skill" >&2; exit 1; }
  src="$TMP/$SKILLS_PATH/$skill"
  target="$DEST/$skill"
  [[ -f "$src/SKILL.md" ]] || { echo "skill '$skill' not found at $TOOLKIT_REF" >&2; exit 1; }
  if find "$src" -type l -print -quit | grep -q .; then
    echo "refusing symlink in skill '$skill'" >&2
    exit 1
  fi
  rm -rf "$target"
  cp -R "$src" "$target"
done < <(python3 -c 'import json,sys; print("\n".join(json.load(open(sys.argv[1]))["skills"]))' "$LOCK")
printf '%s@%s\n' "$TOOLKIT_REPO" "$TOOLKIT_REF" > "$DEST/SOURCE"
echo "Vendored pinned MWAA skills from $TOOLKIT_REF into $DEST"
