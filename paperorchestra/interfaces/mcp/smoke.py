from __future__ import annotations

import argparse
import json
import shlex
from typing import Any

from paperorchestra.interfaces.mcp import smoke_protocol as _protocol
from paperorchestra.interfaces.mcp import smoke_report as _report
from paperorchestra.interfaces.mcp import smoke_server as _server


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
    print(f"  {'OK' if server.get('expected_tools_present') else 'WARN'} expected tools: {', '.join(_server.EXPECTED_TOOLS)}")
    if server.get("status_call_reached_server"):
        print("  OK harmless status tool call reached server")
    evidence_probe = server.get("evidence_bundle_probe") if isinstance(server.get("evidence_bundle_probe"), dict) else {}
    if evidence_probe.get("checked"):
        print(f"  {'OK' if evidence_probe.get('ok') else 'WARN'} evidence bundle probe")
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
        choices=_protocol.TRANSPORT_CHOICES,
        default=_protocol.TRANSPORT_CONTENT_LENGTH,
        help="MCP stdio framing to smoke-test.",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--probe-evidence-bundle",
        action="store_true",
        help="Also call orchestrate(write_evidence=true) and verify a public-safe evidence bundle is written.",
    )
    args = parser.parse_args(argv)
    command_args = shlex.split(args.args) if args.args else None
    report = _report.build_mcp_smoke_report(
        config_path=args.config,
        server_name=args.name,
        command=args.command,
        args=command_args,
        cwd=args.cwd,
        timeout_sec=args.timeout_sec,
        transport=args.transport,
        probe_evidence_bundle=args.probe_evidence_bundle,
    )
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        _print_human(report)
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
