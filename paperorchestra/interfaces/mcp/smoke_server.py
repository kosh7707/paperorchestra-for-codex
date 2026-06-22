from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from paperorchestra.interfaces.mcp.smoke_probe import _probe_evidence_bundle
from paperorchestra.interfaces.mcp.smoke_protocol import McpSmokeProtocol, TRANSPORT_CONTENT_LENGTH, TRANSPORT_NEWLINE

EXPECTED_TOOLS = [
    "status",
    "run_pipeline",
    "compile_current_paper",
    "critique",
    "export_current",
    "quality_gate",
]


@dataclass(frozen=True)
class McpServerSmokeRunner:
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    cwd: str | Path | None = None
    timeout_sec: float = 5.0
    expected_tools: list[str] = field(default_factory=lambda: list(EXPECTED_TOOLS))
    call_status: bool = True
    probe_evidence_bundle: bool = False
    transport: str = TRANSPORT_CONTENT_LENGTH

    def run(self) -> dict[str, Any]:
        protocol = McpSmokeProtocol(self.transport)
        proc = self._start_process()
        assert proc.stdin is not None
        assert proc.stdout is not None
        try:
            protocol.write(proc.stdin, self._initialize_request())
            initialize = protocol.read(proc.stdout, timeout_sec=self.timeout_sec)
            protocol.write(proc.stdin, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
            protocol.write(proc.stdin, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            tools_list = protocol.read(proc.stdout, timeout_sec=self.timeout_sec)
            tools = tools_list.get("result", {}).get("tools", [])
            tool_names = [tool.get("name") for tool in tools if isinstance(tool, dict)]
            missing_tools = [name for name in self.expected_tools if name not in tool_names]

            status_call: dict[str, Any] | None = None
            next_request_id = 3
            if self.call_status:
                protocol.write(proc.stdin, self._status_request(next_request_id))
                status_call = protocol.read(proc.stdout, timeout_sec=self.timeout_sec)
                next_request_id += 1

            evidence_bundle_probe = {"checked": False}
            if self.probe_evidence_bundle:
                evidence_bundle_probe = _probe_evidence_bundle(
                    proc.stdin,
                    proc.stdout,
                    request_id=next_request_id,
                    cwd=Path(self.cwd or ".").resolve(),
                    timeout_sec=self.timeout_sec,
                    transport=self.transport,
                )
            return self._result(initialize, tools, missing_tools, status_call, evidence_bundle_probe)
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        finally:
            self._stop_process(proc)

    def _start_process(self) -> subprocess.Popen[bytes]:
        merged_env = os.environ.copy()
        merged_env.update({str(key): str(value) for key, value in self.env.items()})
        return subprocess.Popen(
            [self.command, *self.args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            cwd=str(self.cwd) if self.cwd else None,
            env=merged_env,
        )

    def _initialize_request(self) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18" if self.transport == TRANSPORT_NEWLINE else "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "paperorchestra-mcp-smoke", "version": "1.1.0"},
            },
        }

    def _status_request(self, request_id: int) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": "status", "arguments": {"cwd": str(Path(self.cwd or ".").resolve())}},
        }

    def _result(
        self,
        initialize: dict[str, Any],
        tools: Any,
        missing_tools: list[str],
        status_call: dict[str, Any] | None,
        evidence_bundle_probe: dict[str, Any],
    ) -> dict[str, Any]:
        initialize_ok = initialize.get("result", {}).get("serverInfo", {}).get("name") == "paperorchestra-mcp"
        tools_list_ok = isinstance(tools, list)
        ok = initialize_ok and tools_list_ok and not missing_tools and (not evidence_bundle_probe.get("checked") or bool(evidence_bundle_probe.get("ok")))
        return {
            "ok": ok,
            "transport": self.transport,
            "initialize_ok": initialize_ok,
            "protocol_version": initialize.get("result", {}).get("protocolVersion"),
            "server_info": initialize.get("result", {}).get("serverInfo"),
            "tools_list_ok": tools_list_ok,
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
            "evidence_bundle_probe": evidence_bundle_probe,
        }

    def _stop_process(self, proc: subprocess.Popen[bytes]) -> None:
        if proc.stdin:
            try:
                proc.stdin.close()
            except BrokenPipeError:
                pass
        try:
            proc.wait(timeout=self.timeout_sec)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=1)


def smoke_mcp_server(
    command: str,
    *,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
    cwd: str | Path | None = None,
    timeout_sec: float = 5.0,
    expected_tools: list[str] | None = None,
    call_status: bool = True,
    probe_evidence_bundle: bool = False,
    transport: str = TRANSPORT_CONTENT_LENGTH,
) -> dict[str, Any]:
    return McpServerSmokeRunner(
        command=command,
        args=args or [],
        env=env or {},
        cwd=cwd,
        timeout_sec=timeout_sec,
        expected_tools=expected_tools or list(EXPECTED_TOOLS),
        call_status=call_status,
        probe_evidence_bundle=probe_evidence_bundle,
        transport=transport,
    ).run()
