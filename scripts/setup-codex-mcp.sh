#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
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
