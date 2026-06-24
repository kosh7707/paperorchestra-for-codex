from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "check-cli-surface.py"


def run_checker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), "--source-root", str(ROOT), *args, "--json"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_cli_surface_checker_verifies_source_visual_audit() -> None:
    result = run_checker("--require", "visual-audit")
    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)

    assert payload["source_origin_matches_checkout"] is True
    assert payload["source_required_missing"] == []
    assert payload["commands"]["visual-audit"]["source_module"]["ok"] is True
    assert "visual-audit" in payload["required_commands"]
    assert "paperorchestra.cli" in payload["recommended_invocation"] or ".venv/bin/paperorchestra" in payload["recommended_invocation"]


def test_cli_surface_checker_strict_installed_exit_matches_report() -> None:
    result = run_checker("--require", "visual-audit", "--strict-installed")
    payload = json.loads(result.stdout)

    expected = 3 if payload["installed_required_missing"] else 0
    assert result.returncode == expected, payload
    assert payload["commands"]["visual-audit"]["source_module"]["ok"] is True
