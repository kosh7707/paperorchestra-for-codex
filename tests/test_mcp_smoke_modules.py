from __future__ import annotations

import io
import json
from pathlib import Path

from paperorchestra.interfaces.mcp import smoke_config, smoke_probe, smoke_protocol, smoke_report


def test_read_codex_mcp_registration_extracts_named_server(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        """
[mcp_servers.paperorchestra]
command = "paperorchestra-mcp"
args = ["--stdio"]
enabled = false
[mcp_servers.paperorchestra.env]
PAPERO_TEST = "1"
""".strip(),
        encoding="utf-8",
    )

    registration = smoke_config.read_codex_mcp_registration(config)

    assert registration["registered"] is True
    assert registration["enabled"] is False
    assert registration["command"] == "paperorchestra-mcp"
    assert registration["args"] == ["--stdio"]
    assert registration["env"] == {"PAPERO_TEST": "1"}


def test_transport_writer_supports_content_length_and_newline() -> None:
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}

    content_length = io.BytesIO()
    smoke_protocol._write_message(content_length, payload)
    raw = content_length.getvalue()
    header, body = raw.split(b"\r\n\r\n", 1)
    assert header == f"Content-Length: {len(body)}".encode("ascii")
    assert json.loads(body.decode("utf-8")) == payload

    newline = io.BytesIO()
    smoke_protocol._write_message(newline, payload, transport=smoke_protocol.TRANSPORT_NEWLINE)
    assert newline.getvalue().endswith(b"\n")
    assert json.loads(newline.getvalue().decode("utf-8")) == payload


def test_bundle_contains_text_only_scans_json_files(tmp_path: Path) -> None:
    output = tmp_path / "bundle"
    output.mkdir()
    (output / "manifest.json").write_text('{"cwd":"/safe/project"}', encoding="utf-8")
    (output / "notes.txt").write_text("/secret/project", encoding="utf-8")

    assert smoke_probe._bundle_contains_text(output, "/safe/project") is True
    assert smoke_probe._bundle_contains_text(output, "/secret/project") is False
    assert smoke_probe._bundle_contains_text(tmp_path / "missing", "/safe/project") is None


def test_build_report_skips_server_when_command_is_missing(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text("[mcp_servers.paperorchestra]\ncommand = \"/definitely/missing/paperorchestra-mcp\"\n", encoding="utf-8")

    report = smoke_report.build_mcp_smoke_report(config_path=config, cwd=tmp_path)

    assert report["status"] == "warning"
    assert report["config"]["registered"] is True
    assert report["binary"]["exists"] is False
    assert report["server"] == {"ok": False, "detail": "Server smoke was skipped because no executable command was found."}
