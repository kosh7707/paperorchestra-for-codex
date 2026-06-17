#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET_ROOT="${1:-$HOME/.codex/skills}"
mkdir -p "$TARGET_ROOT"

for skill_dir in "$ROOT"/skills/*; do
  [ -d "$skill_dir" ] || continue
  skill_name="$(basename "$skill_dir")"
  mkdir -p "$TARGET_ROOT/$skill_name"
  cp "$skill_dir/SKILL.md" "$TARGET_ROOT/$skill_name/SKILL.md"
  if [ -d "$skill_dir/agents" ]; then
    mkdir -p "$TARGET_ROOT/$skill_name/agents"
    cp "$skill_dir/agents"/* "$TARGET_ROOT/$skill_name/agents/"
  fi
  echo "Installed skill to: $TARGET_ROOT/$skill_name/SKILL.md"
done
