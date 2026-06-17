from __future__ import annotations

import json
from pathlib import Path
from typing import Any, BinaryIO

from paperorchestra.interfaces.mcp.smoke_protocol import McpSmokeProtocol, TRANSPORT_CONTENT_LENGTH


class EvidenceBundleProbe:
    """Optional MCP tool-call probe for public-safe evidence bundle output."""

    def __init__(self, *, request_id: int, cwd: Path, timeout_sec: float, transport: str = TRANSPORT_CONTENT_LENGTH) -> None:
        self.request_id = request_id
        self.cwd = cwd
        self.timeout_sec = timeout_sec
        self.protocol = McpSmokeProtocol(transport)

    def run(self, stdin: BinaryIO, stdout: BinaryIO) -> dict[str, Any]:
        self.protocol.write(
            stdin,
            {
                "jsonrpc": "2.0",
                "id": self.request_id,
                "method": "tools/call",
                "params": {"name": "orchestrate", "arguments": {"cwd": str(self.cwd), "write_evidence": True}},
            },
        )
        response = self.protocol.read(stdout, timeout_sec=self.timeout_sec)
        return _evaluate_evidence_bundle_response(response, cwd=self.cwd)


def _probe_evidence_bundle(
    stdin: BinaryIO,
    stdout: BinaryIO,
    *,
    request_id: int,
    cwd: Path,
    timeout_sec: float,
    transport: str,
) -> dict[str, Any]:
    return EvidenceBundleProbe(request_id=request_id, cwd=cwd, timeout_sec=timeout_sec, transport=transport).run(stdin, stdout)


def _evaluate_evidence_bundle_response(response: dict[str, Any], *, cwd: Path) -> dict[str, Any]:
    result = response.get("result", {})
    is_error = bool(result.get("isError")) if isinstance(result, dict) else False
    content = result.get("content") if isinstance(result, dict) else None
    text = content[0].get("text") if isinstance(content, list) and content and isinstance(content[0], dict) else None
    payload: dict[str, Any] = {}
    if isinstance(text, str) and text.strip():
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = {}

    bundle = payload.get("evidence_bundle") if isinstance(payload.get("evidence_bundle"), dict) else {}
    manifest_path = Path(str(bundle.get("manifest_path", ""))) if bundle.get("manifest_path") else None
    output_dir = Path(str(bundle.get("output_dir", ""))) if bundle.get("output_dir") else None
    manifest_exists = bool(manifest_path and manifest_path.exists())
    bundle_contains_cwd = _bundle_contains_text(output_dir, str(cwd)) if output_dir and output_dir.exists() else None
    paper_full_tex_present = "paper_full_tex" in json.dumps(payload, ensure_ascii=False)
    ok = (
        not is_error
        and payload.get("execution") == "bounded_plan_only"
        and manifest_exists
        and paper_full_tex_present is False
        and bundle_contains_cwd is False
    )
    return {
        "checked": True,
        "ok": ok,
        "is_error": is_error,
        "execution": payload.get("execution"),
        "manifest_path": str(manifest_path) if manifest_path else None,
        "output_dir": str(output_dir) if output_dir else None,
        "manifest_exists": manifest_exists,
        "paper_full_tex_present": paper_full_tex_present,
        "bundle_contains_absolute_cwd": bundle_contains_cwd,
    }


def _bundle_contains_text(output_dir: Path | None, needle: str) -> bool | None:
    if output_dir is None or not output_dir.exists():
        return None
    for path in output_dir.rglob("*.json"):
        if needle in path.read_text(encoding="utf-8"):
            return True
    return False
