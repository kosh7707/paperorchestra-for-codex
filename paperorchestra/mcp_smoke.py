from __future__ import annotations

import argparse
import json
import os
import select
import shlex
import shutil
import subprocess
import sys
import time
import tomllib
from pathlib import Path
from typing import Any


EXPECTED_TOOLS = [
    "status",
    "run_pipeline",
    "check_compile_environment",
    "compile_current_paper",
    "audit_reproducibility",
]

TRANSPORT_CONTENT_LENGTH = "content-length"
TRANSPORT_NEWLINE = "newline"
TRANSPORT_CHOICES = (TRANSPORT_CONTENT_LENGTH, TRANSPORT_NEWLINE)


def _readline(stream, timeout_sec: float) -> bytes:
    ready, _, _ = select.select([stream], [], [], timeout_sec)
    if not ready:
        raise TimeoutError("Timed out waiting for MCP server stdout.")
    return stream.readline()


def _read_exact(stream, length: int, timeout_sec: float) -> bytes:
    chunks: list[bytes] = []
    remaining = length
    deadline = time.monotonic() + timeout_sec
    while remaining > 0:
        timeout_remaining = deadline - time.monotonic()
        if timeout_remaining <= 0:
            raise TimeoutError("Timed out waiting for MCP server response body.")
        ready, _, _ = select.select([stream], [], [], timeout_remaining)
        if not ready:
            raise TimeoutError("Timed out waiting for MCP server response body.")
        chunk = os.read(stream.fileno(), remaining)
        if not chunk:
            raise RuntimeError("MCP server closed stdout while reading response body.")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _read_message(stream, *, timeout_sec: float, transport: str = TRANSPORT_CONTENT_LENGTH) -> dict[str, Any]:
    if transport == TRANSPORT_NEWLINE:
        line = _readline(stream, timeout_sec)
        if not line:
            raise RuntimeError("MCP server closed stdout while waiting for newline JSON response.")
        return json.loads(line.decode("utf-8"))
    headers: dict[str, str] = {}
    while True:
        line = _readline(stream, timeout_sec)
        if not line:
            raise RuntimeError("MCP server closed stdout while waiting for headers.")
        if line in (b"\r\n", b"\n"):
            break
        decoded = line.decode("utf-8").strip()
        if ":" in decoded:
            key, value = decoded.split(":", 1)
            headers[key.strip().lower()] = value.strip()
    length = int(headers.get("content-length", "0"))
    if length <= 0:
        raise RuntimeError("MCP server response did not include a positive Content-Length.")
    return json.loads(_read_exact(stream, length, timeout_sec).decode("utf-8"))


def _write_message(stream, payload: dict[str, Any], *, transport: str = TRANSPORT_CONTENT_LENGTH) -> None:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if transport == TRANSPORT_NEWLINE:
        stream.write(raw + b"\n")
    else:
        stream.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii"))
        stream.write(raw)
    stream.flush()


def _config_path(raw: str | Path | None = None) -> Path:
    if raw:
        return Path(raw).expanduser()
    return Path(os.environ.get("CODEX_CONFIG_PATH", "~/.codex/config.toml")).expanduser()


def read_codex_mcp_registration(config_path: str | Path | None = None, *, server_name: str = "paperorchestra") -> dict[str, Any]:
    path = _config_path(config_path)
    result: dict[str, Any] = {
        "config_path": str(path),
        "registered": False,
        "enabled": None,
        "command": None,
        "args": [],
        "env": {},
        "detail": "Codex config not found.",
    }
    if not path.exists():
        return result
    try:
        config = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        result["detail"] = f"Could not parse Codex config TOML: {type(exc).__name__}: {exc}"
        return result

    servers = config.get("mcp_servers")
    if not isinstance(servers, dict) or not isinstance(servers.get(server_name), dict):
        result["detail"] = f"No [mcp_servers.{server_name}] section found."
        return result

    server = servers[server_name]
    command = server.get("command")
    args = server.get("args", [])
    env = server.get("env", {})
    result.update(
        {
            "registered": True,
            "enabled": server.get("enabled", True),
            "command": command if isinstance(command, str) else None,
            "args": args if isinstance(args, list) else [],
            "env": env if isinstance(env, dict) else {},
            "detail": "Codex config registration found.",
        }
    )
    return result


def _command_exists(command: str | None) -> tuple[bool, str | None]:
    if not command:
        return False, None
    if os.sep in command or (os.altsep and os.altsep in command):
        path = Path(command).expanduser()
        return path.exists() and os.access(path, os.X_OK), str(path)
    found = shutil.which(command)
    return bool(found), found


def smoke_mcp_server(
    command: str,
    *,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
    cwd: str | Path | None = None,
    timeout_sec: float = 5.0,
    expected_tools: list[str] | None = None,
    call_status: bool = True,
    transport: str = TRANSPORT_CONTENT_LENGTH,
) -> dict[str, Any]:
    if transport not in TRANSPORT_CHOICES:
        raise ValueError(f"Unsupported MCP smoke transport: {transport}")
    expected_tools = expected_tools or EXPECTED_TOOLS
    argv = [command, *(args or [])]
    merged_env = os.environ.copy()
    if env:
        merged_env.update({str(key): str(value) for key, value in env.items()})
    proc = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
        cwd=str(cwd) if cwd else None,
        env=merged_env,
    )
    assert proc.stdin is not None
    assert proc.stdout is not None
    try:
        _write_message(
            proc.stdin,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18" if transport == TRANSPORT_NEWLINE else "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "paperorchestra-mcp-smoke", "version": "0.1.0"},
                },
            },
            transport=transport,
        )
        initialize = _read_message(proc.stdout, timeout_sec=timeout_sec, transport=transport)
        _write_message(proc.stdin, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}, transport=transport)
        _write_message(proc.stdin, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, transport=transport)
        tools_list = _read_message(proc.stdout, timeout_sec=timeout_sec, transport=transport)
        tools = tools_list.get("result", {}).get("tools", [])
        tool_names = [tool.get("name") for tool in tools if isinstance(tool, dict)]
        missing_tools = [name for name in expected_tools if name not in tool_names]
        status_call: dict[str, Any] | None = None
        if call_status:
            _write_message(
                proc.stdin,
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "status", "arguments": {"cwd": str(Path(cwd or '.').resolve())}}},
                transport=transport,
            )
            status_call = _read_message(proc.stdout, timeout_sec=timeout_sec, transport=transport)
        ok = (
            initialize.get("result", {}).get("serverInfo", {}).get("name") == "paperorchestra-mcp"
            and isinstance(tools, list)
            and not missing_tools
        )
        return {
            "ok": ok,
            "transport": transport,
            "initialize_ok": initialize.get("result", {}).get("serverInfo", {}).get("name") == "paperorchestra-mcp",
            "protocol_version": initialize.get("result", {}).get("protocolVersion"),
            "server_info": initialize.get("result", {}).get("serverInfo"),
            "tools_list_ok": isinstance(tools, list),
            "tool_count": len(tools) if isinstance(tools, list) else 0,
            "expected_tools_present": not missing_tools,
            "missing_expected_tools": missing_tools,
            "status_call_reached_server": status_call is not None and status_call.get("id") == 3,
            "status_call_is_error": status_call.get("result", {}).get("isError") if status_call else None,
            "status_call_text": (
                status_call.get("result", {}).get("content", [{}])[0].get("text")
                if status_call and isinstance(status_call.get("result", {}).get("content"), list)
                else None
            ),
        }
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass
        try:
            proc.wait(timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=1)


def build_mcp_smoke_report(
    *,
    config_path: str | Path | None = None,
    server_name: str = "paperorchestra",
    command: str | None = None,
    args: list[str] | None = None,
    cwd: str | Path | None = None,
    timeout_sec: float = 5.0,
    transport: str = TRANSPORT_CONTENT_LENGTH,
) -> dict[str, Any]:
    registration = read_codex_mcp_registration(config_path, server_name=server_name)
    selected_command = command or registration.get("command") or shutil.which("paperorchestra-mcp")
    selected_args = args if args is not None else list(registration.get("args") or [])
    binary_exists, resolved_command = _command_exists(selected_command)
    server: dict[str, Any] | None = None
    if selected_command and binary_exists:
        server = smoke_mcp_server(
            selected_command,
            args=selected_args,
            env=registration.get("env") if registration.get("registered") else None,
            cwd=cwd,
            timeout_sec=timeout_sec,
            transport=transport,
        )
    return {
        "status": "ok" if registration.get("registered") and binary_exists and server and server.get("ok") else "warning",
        "transport": transport,
        "config": registration,
        "binary": {
            "command": selected_command,
            "args": selected_args,
            "exists": binary_exists,
            "resolved_command": resolved_command,
        },
        "server": server or {"ok": False, "detail": "Server smoke was skipped because no executable command was found."},
        "active_session_attachment": {
            "checked": False,
            "detail": "This script verifies registration and stdio MCP health only. It cannot prove that the current Codex conversation received mcp__paperorchestra__ tools.",
            "if_tools_absent": "If mcp__paperorchestra__ tools are absent but this smoke passes, treat it as a Codex active-session attachment/tool-injection issue and use the CLI fallback while restarting or inspecting Codex attach logs.",
        },
    }


def _print_human(report: dict[str, Any]) -> None:
    config = report["config"]
    binary = report["binary"]
    server = report["server"]
    active = report["active_session_attachment"]
    print("PaperOrchestra MCP smoke result")
    print()
    print("Config:")
    print(f"  {'OK' if config.get('registered') else 'WARN'} registered: {config.get('registered')} ({config.get('config_path')})")
    if config.get("command"):
        print(f"  command: {config.get('command')}")
    print()
    print("Binary:")
    print(f"  {'OK' if binary.get('exists') else 'WARN'} executable: {binary.get('resolved_command') or binary.get('command')}")
    print()
    print("Server:")
    print(f"  {'OK' if server.get('initialize_ok') else 'WARN'} initialize")
    print(f"  {'OK' if server.get('tools_list_ok') else 'WARN'} tools/list ({server.get('tool_count', 0)} tools)")
    print(f"  {'OK' if server.get('expected_tools_present') else 'WARN'} expected tools: {', '.join(EXPECTED_TOOLS)}")
    if server.get("status_call_reached_server"):
        print("  OK harmless status tool call reached server")
    if server.get("missing_expected_tools"):
        print(f"  missing: {', '.join(server['missing_expected_tools'])}")
    if server.get("error"):
        print(f"  error: {server['error']}")
    print()
    print("Active session:")
    print(f"  NOT CHECKED: {active['detail']}")
    print(f"  If absent in Codex: {active['if_tools_absent']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke-test PaperOrchestra MCP registration and stdio server health.")
    parser.add_argument("--config", help="Codex config path. Default: CODEX_CONFIG_PATH or ~/.codex/config.toml")
    parser.add_argument("--name", default="paperorchestra", help="MCP server name in Codex config")
    parser.add_argument("--command", help="Override MCP server command")
    parser.add_argument("--args", default="", help="Extra command args as a shell-like string")
    parser.add_argument("--cwd", default=".", help="Working directory for the MCP server smoke")
    parser.add_argument("--timeout-sec", type=float, default=5.0)
    parser.add_argument(
        "--transport",
        choices=TRANSPORT_CHOICES,
        default=TRANSPORT_CONTENT_LENGTH,
        help="MCP stdio framing to smoke-test.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    command_args = shlex.split(args.args) if args.args else None
    report = build_mcp_smoke_report(
        config_path=args.config,
        server_name=args.name,
        command=args.command,
        args=command_args,
        cwd=args.cwd,
        timeout_sec=args.timeout_sec,
        transport=args.transport,
    )
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        _print_human(report)
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
