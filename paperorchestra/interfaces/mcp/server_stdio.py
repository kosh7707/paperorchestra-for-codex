from __future__ import annotations

import json
import sys
from collections.abc import Callable, Mapping
from typing import Any

JSON = dict[str, Any]
ToolHandler = Callable[[JSON], JSON]

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


def _handle_request(
    message: JSON,
    *,
    tools: list[JSON],
    handlers: Mapping[str, ToolHandler],
    server_info: JSON,
) -> JSON | None:
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params", {}) or {}

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": _negotiate_protocol_version(params),
                "serverInfo": server_info,
                "capabilities": {"tools": {}},
            },
        }
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": tools}}
    if method == "tools/call":
        return _handle_tool_call(request_id, params, handlers)
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}


def _handle_tool_call(request_id: Any, params: JSON, handlers: Mapping[str, ToolHandler]) -> JSON:
    name = params.get("name")
    arguments = params.get("arguments", {}) or {}
    handler = handlers.get(str(name))
    if handler is None:
        return {"jsonrpc": "2.0", "id": request_id, "result": _err(f"Unknown tool: {name}")}
    try:
        result = handler(arguments)
    except Exception as exc:
        result = _err(f"{type(exc).__name__}: {exc}")
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def serve_stdio(*, tools: list[JSON], handlers: Mapping[str, ToolHandler], server_info: JSON) -> int:
    while True:
        message = _read_message()
        if message is None:
            return 0
        response = _handle_request(message, tools=tools, handlers=handlers, server_info=server_info)
        if response is not None:
            _write_message(response)


__all__ = [
    "JSON",
    "MCP_PROTOCOL_DEFAULT",
    "MCP_PROTOCOL_SUPPORTED",
    "_err",
    "_handle_request",
    "_negotiate_protocol_version",
    "_read_message",
    "_write_message",
    "serve_stdio",
]
