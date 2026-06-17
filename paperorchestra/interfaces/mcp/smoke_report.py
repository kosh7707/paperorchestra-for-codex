from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paperorchestra.interfaces.mcp.smoke_config import _command_exists, read_codex_mcp_registration
from paperorchestra.interfaces.mcp.smoke_protocol import TRANSPORT_CONTENT_LENGTH
from paperorchestra.interfaces.mcp.smoke_server import smoke_mcp_server


@dataclass(frozen=True)
class McpSmokeReportBuilder:
    config_path: str | Path | None = None
    server_name: str = "paperorchestra"
    command: str | None = None
    args: list[str] | None = None
    cwd: str | Path | None = None
    timeout_sec: float = 5.0
    transport: str = TRANSPORT_CONTENT_LENGTH
    probe_evidence_bundle: bool = False

    def build(self) -> dict[str, Any]:
        registration = read_codex_mcp_registration(self.config_path, server_name=self.server_name)
        selected_command = self.command or registration.get("command") or shutil.which("paperorchestra-mcp")
        selected_args = self.args if self.args is not None else list(registration.get("args") or [])
        binary_exists, resolved_command = _command_exists(selected_command)
        server: dict[str, Any] | None = None
        if selected_command and binary_exists:
            server = smoke_mcp_server(
                selected_command,
                args=selected_args,
                env=registration.get("env") if registration.get("registered") else None,
                cwd=self.cwd,
                timeout_sec=self.timeout_sec,
                transport=self.transport,
                probe_evidence_bundle=self.probe_evidence_bundle,
            )
        return {
            "status": "ok" if registration.get("registered") and binary_exists and server and server.get("ok") else "warning",
            "transport": self.transport,
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


def build_mcp_smoke_report(
    *,
    config_path: str | Path | None = None,
    server_name: str = "paperorchestra",
    command: str | None = None,
    args: list[str] | None = None,
    cwd: str | Path | None = None,
    timeout_sec: float = 5.0,
    transport: str = TRANSPORT_CONTENT_LENGTH,
    probe_evidence_bundle: bool = False,
) -> dict[str, Any]:
    return McpSmokeReportBuilder(
        config_path=config_path,
        server_name=server_name,
        command=command,
        args=args,
        cwd=cwd,
        timeout_sec=timeout_sec,
        transport=transport,
        probe_evidence_bundle=probe_evidence_bundle,
    ).build()
