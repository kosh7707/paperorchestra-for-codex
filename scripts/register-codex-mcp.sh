#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG_PATH="${CODEX_CONFIG_PATH:-$HOME/.codex/config.toml}"
SERVER_NAME="paperorchestra"
COMMAND="paperorchestra-mcp"
USE_LOCAL_VENV=0
DRY_RUN=0
BACKUP=1
STARTUP_TIMEOUT_SEC=10
ALLOWED_PROVIDER_BINARIES="codex,openai,ollama,llm,claude,gemini"

usage() {
  cat <<'USAGE'
Usage: scripts/register-codex-mcp.sh [options]

Register the PaperOrchestra MCP server in Codex CLI's TOML config.

Options:
  --use-local-venv
      Register this checkout's .venv/bin/paperorchestra-mcp absolute path.
      Run `python -m pip install -e .` or `python -m pip install -e ".[dev]"`
      first if the venv command does not exist.

  --command PATH_OR_NAME
      Register an explicit command instead of paperorchestra-mcp.

  --config PATH
      Codex CLI config path. Default: $CODEX_CONFIG_PATH or ~/.codex/config.toml.

  --name NAME
      MCP server name. Default: paperorchestra.

  --allowed-provider-binaries LIST
      Value for PAPERO_ALLOWED_PROVIDER_BINARIES.
      Default: codex,openai,ollama,llm,claude,gemini.

  --startup-timeout-sec N
      startup_timeout_sec value. Default: 10.

  --dry-run
      Print the resulting config to stdout; do not write files.

  --no-backup
      Do not create a timestamped .bak file before writing an existing config.

  --codex-cli
      Accepted as a compatibility no-op so callers can use the same option
      shape as scripts/setup-codex-mcp.sh --codex-cli.

  -h, --help
      Show this help.

The script is idempotent for the target server. It removes any existing
[mcp_servers.<name>] and [mcp_servers.<name>.env] sections before appending the
new registration. Other config sections are preserved. Existing configs are
backed up by default.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --use-local-venv)
      USE_LOCAL_VENV=1
      ;;
    --command)
      COMMAND="${2:?--command requires a value}"
      shift
      ;;
    --config)
      CONFIG_PATH="${2:?--config requires a value}"
      shift
      ;;
    --name)
      SERVER_NAME="${2:?--name requires a value}"
      shift
      ;;
    --allowed-provider-binaries)
      ALLOWED_PROVIDER_BINARIES="${2:?--allowed-provider-binaries requires a value}"
      shift
      ;;
    --startup-timeout-sec)
      STARTUP_TIMEOUT_SEC="${2:?--startup-timeout-sec requires a value}"
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      ;;
    --no-backup)
      BACKUP=0
      ;;
    --codex-cli)
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 64
      ;;
  esac
  shift
done

if [[ "$USE_LOCAL_VENV" == "1" ]]; then
  COMMAND="$ROOT/.venv/bin/paperorchestra-mcp"
  if [[ ! -x "$COMMAND" ]]; then
    cat >&2 <<EOF
ERROR: local venv MCP binary not found or not executable:
  $COMMAND

Run one of these first:
  python3 -m venv .venv
  source .venv/bin/activate
  python -m pip install -e .

Or pass --command /absolute/path/to/paperorchestra-mcp.
EOF
    exit 66
  fi
fi

if ! [[ "$STARTUP_TIMEOUT_SEC" =~ ^[0-9]+$ ]] || [[ "$STARTUP_TIMEOUT_SEC" -lt 1 ]]; then
  echo "ERROR: --startup-timeout-sec must be a positive integer." >&2
  exit 64
fi

if [[ "$SERVER_NAME" =~ [^A-Za-z0-9_-] ]]; then
  echo "ERROR: --name may only contain letters, numbers, underscore, or dash." >&2
  exit 64
fi

export CONFIG_PATH SERVER_NAME COMMAND ALLOWED_PROVIDER_BINARIES STARTUP_TIMEOUT_SEC DRY_RUN BACKUP
python3 - <<'PY'
from __future__ import annotations

import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

config_path = Path(os.environ["CONFIG_PATH"]).expanduser()
server = os.environ["SERVER_NAME"]
command = os.environ["COMMAND"]
allowed_provider_binaries = os.environ["ALLOWED_PROVIDER_BINARIES"]
startup_timeout_sec = int(os.environ["STARTUP_TIMEOUT_SEC"])
dry_run = os.environ["DRY_RUN"] == "1"
backup = os.environ["BACKUP"] == "1"

section_names = {f"mcp_servers.{server}", f"mcp_servers.{server}.env"}
section_re = re.compile(r"^\s*\[([^\]]+)\]\s*(?:#.*)?$")
begin_marker = f"# BEGIN PaperOrchestra MCP server {server} (managed by scripts/register-codex-mcp.sh)"
end_marker = f"# END PaperOrchestra MCP server {server}"


def strip_managed_block(lines: list[str]) -> list[str]:
    output: list[str] = []
    skipping = False
    for line in lines:
        if line.rstrip("\n") == begin_marker:
            skipping = True
            continue
        if skipping and line.rstrip("\n") == end_marker:
            skipping = False
            continue
        if not skipping:
            output.append(line)
    return output


def strip_sections(lines: list[str]) -> list[str]:
    output: list[str] = []
    skip_section = False
    for line in lines:
        match = section_re.match(line)
        if match:
            skip_section = match.group(1).strip() in section_names
        if not skip_section:
            output.append(line)
    while output and not output[-1].strip():
        output.pop()
    return output


def toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


existing = config_path.read_text(encoding="utf-8").splitlines(keepends=True) if config_path.exists() else []
preserved = strip_sections(strip_managed_block(existing))
block = [
    "\n" if preserved else "",
    f"{begin_marker}\n",
    f"[mcp_servers.{server}]\n",
    f"command = {toml_string(command)}\n",
    "enabled = true\n",
    f"startup_timeout_sec = {startup_timeout_sec}\n",
    "\n",
    f"[mcp_servers.{server}.env]\n",
    f"PAPERO_ALLOWED_PROVIDER_BINARIES = {toml_string(allowed_provider_binaries)}\n",
    f"{end_marker}\n",
]
new_text = "".join(preserved + block)

if dry_run:
    sys.stdout.write(new_text)
    sys.stderr.write(f"[dry-run] would write Codex MCP config: {config_path}\n")
    sys.stderr.write(f"[dry-run] command: {command}\n")
    raise SystemExit(0)

config_path.parent.mkdir(parents=True, exist_ok=True)
if config_path.exists() and backup:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    backup_path = config_path.with_name(f"{config_path.name}.bak.{stamp}")
    shutil.copy2(config_path, backup_path)
    sys.stderr.write(f"Backed up existing config to: {backup_path}\n")

config_path.write_text(new_text, encoding="utf-8")
sys.stderr.write(f"Registered PaperOrchestra MCP server '{server}' in: {config_path}\n")
sys.stderr.write(f"Command: {command}\n")
sys.stderr.write("Next:\n")
sys.stderr.write("  1. Restart Codex completely so it reloads MCP servers.\n")
sys.stderr.write("  2. In the new session, verify that mcp__paperorchestra__status or mcp__paperorchestra__check_compile_environment is visible.\n")
sys.stderr.write("  3. If tools are absent, run: scripts/smoke-paperorchestra-mcp.py\n")
sys.stderr.write("Note: `codex mcp list` shows config registration, not active session attachment/tool injection.\n")
PY
