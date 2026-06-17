#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

DRY_RUN=0
WITH_DEMO=0
WITH_MCP=0
DEV_INSTALL=0
SKIP_SKILLS=0

usage() {
  cat <<'USAGE'
PaperOrchestra installer

Usage:
  ./install.sh [--demo] [--mcp] [--dev] [--skip-skills] [--dry-run]

What it does by default:
  - creates .venv if needed
  - installs PaperOrchestra into .venv
  - installs all bundled Codex skills into ~/.codex/skills
  - prints the next commands

Options:
  --demo         also run the safe mock demo after install
  --mcp          also register the PaperOrchestra MCP server for Codex CLI
  --dev          install dev extras for tests/contributor work
  --skip-skills  skip Codex skill installation
  --dry-run      print the plan without changing files
  -h, --help     show this help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --demo) WITH_DEMO=1 ;;
    --mcp) WITH_MCP=1 ;;
    --dev) DEV_INSTALL=1 ;;
    --skip-skills) SKIP_SKILLS=1 ;;
    --dry-run) DRY_RUN=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

find_python() {
  if [[ -n "${PYTHON:-}" ]]; then
    printf '%s\n' "$PYTHON"
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    command -v python
    return 0
  fi
  echo "Python 3.11+ is required but no python3/python was found on PATH." >&2
  return 1
}

print_step() {
  printf '\n==> %s\n' "$1"
}

run() {
  printf '+ '
  printf '%q ' "$@"
  printf '\n'
  if [[ "$DRY_RUN" -eq 0 ]]; then
    "$@"
  fi
}

PYTHON_BIN="$(find_python)"
INSTALL_TARGET="."
if [[ "$DEV_INSTALL" -eq 1 ]]; then
  INSTALL_TARGET=".[dev]"
fi

printf 'PaperOrchestra installer\n'
printf 'Repository: %s\n' "$ROOT"
if [[ "$DRY_RUN" -eq 1 ]]; then
  printf 'Mode: dry-run\n'
fi

print_step "Create local virtualenv"
echo "plan: python -m venv .venv"
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  run "$PYTHON_BIN" -m venv "$ROOT/.venv"
else
  echo "+ .venv already exists"
fi

print_step "Install package"
echo "plan: pip install -e '$INSTALL_TARGET'"
run "$ROOT/.venv/bin/python" -m pip install -e "$INSTALL_TARGET"

if [[ "$SKIP_SKILLS" -eq 0 ]]; then
  print_step "Install Codex skills"
  echo "plan: scripts/install-skill.sh"
  run bash "$ROOT/scripts/install-skill.sh"
else
  print_step "Skip Codex skills"
fi

if [[ "$WITH_MCP" -eq 1 ]]; then
  print_step "Register Codex MCP server"
  echo "plan: scripts/register-codex-mcp.sh --use-local-venv"
  run bash "$ROOT/scripts/register-codex-mcp.sh" --use-local-venv
fi

if [[ "$WITH_DEMO" -eq 1 ]]; then
  print_step "Run safe mock demo"
  echo "plan: scripts/demo-mock.sh --in-repo"
  run bash "$ROOT/scripts/demo-mock.sh" --in-repo
fi

cat <<EOF_NEXT

Next:
  .venv/bin/paperorchestra first-use --intent how_to_use
  .venv/bin/paperorchestra status --json

Optional:
  ./install.sh --demo      # install + safe mock demo
  ./install.sh --mcp       # install + Codex MCP registration, then restart Codex
  ./install.sh --dev       # install dev extras for tests

For live review, set PAPERO_MODEL_CMD when you are ready. S2 is optional.
EOF_NEXT
