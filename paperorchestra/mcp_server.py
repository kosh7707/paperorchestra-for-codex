from __future__ import annotations

import json
import sys
from typing import Any

from paperorchestra.interfaces.mcp.authoring_tool_definitions import AUTHORING_TOOLS
from paperorchestra.interfaces.mcp.handlers import TOOL_HANDLERS
from paperorchestra.interfaces.mcp.quality_tool_definitions import QUALITY_TOOLS
from paperorchestra.interfaces.mcp.tool_schema import _schema

JSON = dict[str, Any]

SESSION_TOOLS: list[JSON] = [
    {
        "name": "status",
        "description": "Return the current PaperOrchestra session state.",
        "inputSchema": _schema({"cwd": {"type": "string"}}),
    },
    {
        "name": "init_session",
        "description": "Initialize a PaperOrchestra session from input files.",
        "inputSchema": _schema(
            {
                "cwd": {"type": "string"},
                "idea": {"type": "string"},
                "experimental_log": {"type": "string"},
                "template": {"type": "string"},
                "guidelines": {"type": "string"},
                "figures_dir": {"type": "string"},
                "cutoff_date": {"type": "string"},
                "venue": {"type": "string"},
                "page_limit": {"type": "integer"},
                "allow_outside_workspace": {"type": "boolean"},
            },
            ["idea", "experimental_log", "template", "guidelines"],
        ),
    },
    {
        "name": "inspect_state",
        "description": "Inspect material readiness and next orchestration actions without live work.",
        "inputSchema": _schema({"cwd": {"type": "string"}, "material": {"type": "string"}}),
    },
]

UTILITY_TOOLS: list[JSON] = [
    {
        "name": "export_current",
        "description": "Copy current manuscript outputs to a destination directory.",
        "inputSchema": _schema(
            {
                "cwd": {"type": "string"},
                "output": {"type": "string"},
                "include_all_artifacts": {"type": "boolean"},
            },
            ["output"],
        ),
    },
    {
        "name": "run_pipeline",
        "description": "Run the full PaperOrchestra pipeline.",
        "inputSchema": _schema(
            {
                "cwd": {"type": "string"},
                "provider": {"type": "string"},
                "provider_command": {"type": "string"},
                "discovery_mode": {"type": "string"},
                "verify_mode": {"type": "string"},
                "verify_error_policy": {"type": "string"},
                "verify_fallback_mode": {"type": "string"},
                "require_live_verification": {"type": "boolean"},
                "refine_iterations": {"type": "integer"},
                "compile_paper": {"type": "boolean"},
                "runtime_mode": {"type": "string"},
            }
        ),
    },
]

TOOLS: list[JSON] = [
    *SESSION_TOOLS,
    *AUTHORING_TOOLS,
    *QUALITY_TOOLS,
    *UTILITY_TOOLS,
]

SERVER_INFO = {"name": "paperorchestra-mcp", "version": "0.1.0"}
MCP_PROTOCOL_SUPPORTED = {"2024-11-05", "2025-06-18"}
MCP_PROTOCOL_DEFAULT = "2024-11-05"
_CURRENT_STDIO_FRAMING = "content-length"


def _err(message: str) -> JSON:
    return {"content": [{"type": "text", "text": message}], "isError": True}


def _negotiate_protocol_version(params: JSON) -> str:
    requested = params.get("protocolVersion")
    if isinstance(requested, str) and requested in MCP_PROTOCOL_SUPPORTED:
        return requested
    return MCP_PROTOCOL_DEFAULT


def _read_message() -> JSON | None:
    global _CURRENT_STDIO_FRAMING
    headers: dict[str, str] = {}
    line = sys.stdin.buffer.readline()
    while True:
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            line = sys.stdin.buffer.readline()
            continue
        if line.lstrip().startswith(b"{"):
            _CURRENT_STDIO_FRAMING = "newline"
            return json.loads(line.decode("utf-8"))
        break
    while True:
        if line in (b"\r\n", b"\n"):
            break
        decoded = line.decode("utf-8").strip()
        if ":" in decoded:
            key, value = decoded.split(":", 1)
            headers[key.strip().lower()] = value.strip()
        line = sys.stdin.buffer.readline()
        if not line:
            return None
    _CURRENT_STDIO_FRAMING = "content-length"
    length = int(headers.get("content-length", "0"))
    if length <= 0:
        return None
    return json.loads(sys.stdin.buffer.read(length).decode("utf-8"))


def _write_message(payload: JSON) -> None:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if _CURRENT_STDIO_FRAMING == "newline":
        sys.stdout.buffer.write(raw + b"\n")
    else:
        sys.stdout.buffer.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii"))
        sys.stdout.buffer.write(raw)
    sys.stdout.buffer.flush()


def _handle_request(message: JSON) -> JSON | None:
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params", {}) or {}

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": _negotiate_protocol_version(params),
                "serverInfo": SERVER_INFO,
                "capabilities": {"tools": {}},
            },
        }
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments", {}) or {}
        handler = TOOL_HANDLERS.get(name)
        if handler is None:
            return {"jsonrpc": "2.0", "id": request_id, "result": _err(f"Unknown tool: {name}")}
        try:
            result = handler(arguments)
        except Exception as exc:
            result = _err(f"{type(exc).__name__}: {exc}")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}


def main() -> int:
    while True:
        message = _read_message()
        if message is None:
            return 0
        response = _handle_request(message)
        if response is not None:
            _write_message(response)


if __name__ == "__main__":
    raise SystemExit(main())
