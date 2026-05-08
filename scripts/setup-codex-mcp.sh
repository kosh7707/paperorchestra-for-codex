#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

for arg in "$@"; do
  if [[ "$arg" == "--codex-cli" ]]; then
    exec "$ROOT/scripts/register-codex-mcp.sh" "$@"
  fi
done

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  cat <<'USAGE'
Usage:
  scripts/setup-codex-mcp.sh [TARGET_DIR]
      Write a JSON-style example MCP config to TARGET_DIR
      (default: ~/.codex/paperorchestra-mcp-config.json).

  scripts/setup-codex-mcp.sh --codex-cli [register options]
      Register PaperOrchestra directly in Codex CLI TOML config by delegating
      to scripts/register-codex-mcp.sh.

Examples:
  scripts/setup-codex-mcp.sh
  scripts/setup-codex-mcp.sh --codex-cli --use-local-venv
  scripts/register-codex-mcp.sh --dry-run --use-local-venv
USAGE
  exit 0
fi

TARGET_DIR="${1:-$HOME/.codex}"
MCP_DIR="$TARGET_DIR"
CONFIG_PATH="$MCP_DIR/paperorchestra-mcp-config.json"

mkdir -p "$MCP_DIR"
cat > "$CONFIG_PATH" <<JSON
{
  "mcpServers": {
    "paperorchestra": {
      "command": "paperorchestra-mcp",
      "args": [],
      "env": {
        "SEMANTIC_SCHOLAR_API_KEY": "<optional>",
        "PAPERO_ALLOWED_PROVIDER_BINARIES": "codex,openai,ollama,llm,claude,gemini"
      }
    }
  }
}
JSON

echo "Wrote MCP example config to: $CONFIG_PATH"
echo "Merge or copy this into your Codex MCP config as needed."
echo "For Codex CLI TOML auto-registration, run:"
echo "  $ROOT/scripts/register-codex-mcp.sh --use-local-venv"
