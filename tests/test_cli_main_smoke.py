from __future__ import annotations

import json
from pathlib import Path

from paperorchestra import cli


def _write(path: Path, text: str = "x") -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_cli_init_status_and_export_current_smoke(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    idea = _write(tmp_path / "idea.md")
    experimental = _write(tmp_path / "experimental.md")
    template = _write(tmp_path / "template.tex", "\\documentclass{article}")
    guidelines = _write(tmp_path / "guidelines.md")

    assert cli.main(
        [
            "init",
            "--idea",
            str(idea),
            "--experimental-log",
            str(experimental),
            "--template",
            str(template),
            "--guidelines",
            str(guidelines),
        ]
    ) == 0
    session_id = capsys.readouterr().out.strip()
    assert session_id.startswith("po-")

    assert cli.main(["status", "--json"]) == 0
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["session_id"] == session_id
    assert status_payload["session_recovery"]["status"] == "actionable"

    export_dir = tmp_path / "overleaf"
    assert cli.main(["export-current", "--output", str(export_dir), "--json"]) == 0
    export_payload = json.loads(capsys.readouterr().out)
    assert export_payload["session_id"] == session_id
    assert export_payload["output_dir"] == str(export_dir.resolve())
