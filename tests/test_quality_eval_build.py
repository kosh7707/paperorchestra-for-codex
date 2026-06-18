from __future__ import annotations

from pathlib import Path

from paperorchestra.core.models import ArtifactIndex, InputBundle, SessionState
from paperorchestra.core.session import save_session, set_current_session
from paperorchestra.loop_engine.quality.eval import build_quality_eval


def _save_minimal_session(tmp_path: Path) -> None:
    state = SessionState(
        session_id="quality-session",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        current_phase="test",
        active_artifact=None,
        inputs=InputBundle(
            idea_path="idea.md",
            experimental_log_path="experimental.md",
            template_path="template.tex",
            guidelines_path="guidelines.md",
        ),
        artifacts=ArtifactIndex(),
    )
    save_session(tmp_path, state)
    set_current_session(tmp_path, state.session_id)


def test_build_quality_eval_handles_minimal_missing_paper_session(tmp_path: Path) -> None:
    _save_minimal_session(tmp_path)

    payload = build_quality_eval(
        tmp_path,
        reproducibility={"strict_content_gate_issues": [], "prompt_trace_file_count": 0},
        fidelity={"overall_status": "missing"},
    )

    assert payload["schema_version"] == "quality-eval/1"
    assert payload["session_id"] == "quality-session"
    assert payload["tiers"]["tier_0_preconditions"]["status"] == "fail"
    assert payload["tiers"]["tier_1_structural"]["status"] == "skipped_due_to_upstream_fail"
    assert payload["source_artifacts"]["citation_support_review"].endswith("citation_support_review.json")
    assert payload["audit_snapshot_hashes"]["reproducibility"].startswith("sha256:")
    assert payload["cross_iteration"]["budget"]["current_attempt_consumes_budget"] is False
