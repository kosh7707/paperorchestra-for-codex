from __future__ import annotations

import json
from pathlib import Path

from paperorchestra.interfaces import cli_output


def test_status_summary_prefers_recovery_next_commands(tmp_path: Path) -> None:
    payload = {
        "session_id": "sess",
        "current_phase": "drafting",
        "artifacts": {"paper_full_tex": str(tmp_path / "paper.full.tex")},
        "session_recovery": {"next_commands": ["paperorchestra critique"]},
    }

    lines = cli_output.status_summary_lines(tmp_path, payload)

    assert "Session: sess" in lines
    assert f"  TeX: {tmp_path / 'paper.full.tex'}" in lines
    assert "  paperorchestra critique" in lines
    assert "  PAPERO_ALLOW_TEX_COMPILE=1 paperorchestra compile" not in lines


def test_environment_summary_renders_readiness_and_mcp_status() -> None:
    lines = cli_output.environment_summary_lines(
        {
            "package_context": {
                "python_executable": "/venv/bin/python",
                "package_root": "/repo/paperorchestra",
            },
            "readiness_profiles": [
                {"name": "codex", "ready": True, "status": "ready"},
                {"name": "latex", "ready": False, "status": "missing", "missing": ["pdflatex"]},
            ],
            "paperorchestra_mcp_health": {
                "config": {"registered": True},
                "server": {"ok": False},
                "active_session_attachment": {"detail": "manual check"},
            },
        }
    )

    assert "  OK codex: ready" in lines
    assert "  WARN latex: missing" in lines
    assert "    missing: pdflatex" in lines
    assert "  OK config registered: True" in lines
    assert "  WARN stdio server health: False" in lines


def test_print_orchestrator_payload_supports_json_and_summary(capsys) -> None:
    payload = {
        "execution": "ran",
        "action_taken": "inspect",
        "execution_record": {
            "status": "ok",
            "adapter": "local",
            "reason": "done",
            "state_rebuild_required": False,
        },
        "state": {
            "next_actions": [{"action_type": "quality_gate"}],
            "readiness": {"label": "ready"},
            "scorecard_summary": {},
        },
    }

    cli_output.print_orchestrator_payload(payload, json_output=False)
    summary = capsys.readouterr().out
    assert "Execution: ran" in summary
    assert "Next action: quality_gate" in summary

    cli_output.print_orchestrator_payload(payload, json_output=True)
    raw_json = capsys.readouterr().out
    assert json.loads(raw_json)["action_taken"] == "inspect"
