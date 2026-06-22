from __future__ import annotations

from pathlib import Path

from paperorchestra.core.models import InputBundle
from paperorchestra.core.session import create_session
from paperorchestra.engine.plan_gate import approve_plan
from paperorchestra.interfaces.status_payload import build_session_status_payload


def test_status_payload_reports_plan_and_skeleton_states(tmp_path: Path) -> None:
    plan = "---\nschema: paperorchestra/paper-plan/3\nrevision: 1\n---\n# Plan\n"
    (tmp_path / "paper-plan.md").write_text(plan, encoding="utf-8")
    approve_plan(tmp_path)
    for name in ("idea.md", "experiment.md", "template.tex", "guide.md"):
        (tmp_path / name).write_text("x", encoding="utf-8")
    create_session(
        tmp_path,
        InputBundle(
            idea_path=str(tmp_path / "idea.md"),
            experimental_log_path=str(tmp_path / "experiment.md"),
            template_path=str(tmp_path / "template.tex"),
            guidelines_path=str(tmp_path / "guide.md"),
        ),
    )

    payload = build_session_status_payload(tmp_path)

    assert payload["plan_gate"]["reason"] == "paper_plan_approved"
    assert payload["plan_gate"]["approval_state"] == "approved_sidecar"
    assert payload["paper_skeleton"]["status"] == "missing"
