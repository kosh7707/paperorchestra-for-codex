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
  for resource_dir in agents references scripts assets; do
    rm -rf "$TARGET_ROOT/$skill_name/$resource_dir"
    if [ -d "$skill_dir/$resource_dir" ]; then
      mkdir -p "$TARGET_ROOT/$skill_name/$resource_dir"
      cp -R "$skill_dir/$resource_dir"/. "$TARGET_ROOT/$skill_name/$resource_dir/"
    fi
  done
  echo "Installed skill to: $TARGET_ROOT/$skill_name/SKILL.md"
done
