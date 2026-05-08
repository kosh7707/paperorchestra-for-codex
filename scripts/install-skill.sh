#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET_DIR="${1:-$HOME/.codex/skills/paperorchestra}"
mkdir -p "$TARGET_DIR"
cp "$ROOT/skills/paperorchestra/SKILL.md" "$TARGET_DIR/SKILL.md"
echo "Installed skill to: $TARGET_DIR/SKILL.md"
