#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CWD="${PAPERO_ATTACH_SMOKE_CWD:-$ROOT}"
CODEX_BIN="${CODEX_BIN:-codex}"
MCP_COMMAND="${PAPERO_MCP_COMMAND:-$ROOT/.venv/bin/paperorchestra-mcp}"
STARTUP_TIMEOUT_SEC="${PAPERO_MCP_STARTUP_TIMEOUT_SEC:-20}"
# Set PAPERO_ATTACH_SMOKE_TOOL=inspect_state to verify a high-level orchestrator MCP tool.
TOOL_NAME="${PAPERO_ATTACH_SMOKE_TOOL:-status}"
EVIDENCE_DIR="${PAPERO_ATTACH_SMOKE_EVIDENCE_DIR:-$(mktemp -d "${TMPDIR:-/tmp}/paperorchestra-codex-mcp-attach.XXXXXX")}"
mkdir -p "$EVIDENCE_DIR"
JSONL="$EVIDENCE_DIR/codex-mcp-attach.jsonl"
REPORT="$EVIDENCE_DIR/codex-mcp-attach-report.json"
VERSION_FILE="$EVIDENCE_DIR/codex-version.txt"

json_string() {
  python3 -c 'import json, sys; print(json.dumps(sys.argv[1]))' "$1"
}

COMMAND_TOML="$(json_string "$MCP_COMMAND")"
CWD_TOML="$(json_string "$CWD")"
TOOL_TOML="$(json_string "$TOOL_NAME")"

if [[ ! -x "$MCP_COMMAND" ]]; then
  python3 - <<PY
import json
from pathlib import Path
report = {
    "status": "blocked",
    "blocker": "mcp_command_not_executable",
    "mcp_command": "$MCP_COMMAND",
    "jsonl": "$JSONL",
}
Path("$REPORT").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
PY
  exit 2
fi

if ! command -v "$CODEX_BIN" >/dev/null 2>&1; then
  python3 - <<PY
import json
from pathlib import Path
report = {"status": "blocked", "blocker": "codex_not_found", "codex_bin": "$CODEX_BIN", "jsonl": "$JSONL"}
Path("$REPORT").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
PY
  exit 2
fi

"$CODEX_BIN" --version >"$VERSION_FILE" 2>&1 || true

set +e
"$CODEX_BIN" exec \
  --json \
  --ignore-user-config \
  --dangerously-bypass-approvals-and-sandbox \
  --skip-git-repo-check \
  -C "$CWD" \
  -c "mcp_servers.paperorchestra.command=$COMMAND_TOML" \
  -c 'mcp_servers.paperorchestra.args=[]' \
  -c 'mcp_servers.paperorchestra.enabled=true' \
  -c "mcp_servers.paperorchestra.startup_timeout_sec=$STARTUP_TIMEOUT_SEC" \
  -c 'mcp_servers.paperorchestra.env.PAPERO_ALLOWED_PROVIDER_BINARIES="codex,openai,ollama,llm,claude,gemini"' \
  "You must call the PaperOrchestra MCP tool named $TOOL_TOML exactly once for cwd $CWD_TOML. If the tool returns a domain-level error because no session exists, stop after reporting that result." \
  >"$JSONL" 2>"$EVIDENCE_DIR/codex-mcp-attach.stderr"
RC=$?
set -e

python3 - <<PY
import json
from pathlib import Path
jsonl = Path("$JSONL")
report_path = Path("$REPORT")
version = Path("$VERSION_FILE").read_text(encoding="utf-8", errors="replace").strip() if Path("$VERSION_FILE").exists() else ""
found = False
matches = []
if jsonl.exists():
    for line in jsonl.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            obj = json.loads(line)
        except Exception:
            continue
        candidates = [obj]
        if isinstance(obj.get("item"), dict):
            candidates.append(obj["item"])
        for item in candidates:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "mcp_tool_call" and item.get("server") == "paperorchestra" and item.get("tool") == "$TOOL_NAME":
                found = True
                matches.append(item)
report = {
    "status": "ok" if found else "blocked",
    "codex_return_code": $RC,
    "codex_version": version,
    "jsonl": str(jsonl),
    "stderr": "$EVIDENCE_DIR/codex-mcp-attach.stderr",
    "mcp_command": "$MCP_COMMAND",
    "cwd": "$CWD",
    "tool_name": "$TOOL_NAME",
    "mcp_tool_call_found": found,
    "matches": matches,
    "config_mutation": "none; this script uses codex exec -c overrides with --ignore-user-config",
}
report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(report, indent=2, ensure_ascii=False))
raise SystemExit(0 if found else 2)
PY
