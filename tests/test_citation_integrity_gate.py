from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from paperorchestra.core.models import ArtifactIndex, InputBundle, SessionState, utc_now_iso
from paperorchestra.core.session import save_session, set_current_session
from paperorchestra.reviews import citation_integrity, citation_integrity_gate, citation_integrity_paths


def _write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_session(tmp_path: Path) -> Path:
    paper_path = tmp_path / "paper.tex"
    paper_path.write_text("Paper body with citation \\cite{A}.", encoding="utf-8")
    now = utc_now_iso()
    state = SessionState(
        session_id="citation-gate-test",
        created_at=now,
        updated_at=now,
        current_phase="review",
        active_artifact="paper.tex",
        inputs=InputBundle(
            idea_path=str(tmp_path / "idea.md"),
            experimental_log_path=str(tmp_path / "log.md"),
            template_path=str(tmp_path / "template.tex"),
            guidelines_path=str(tmp_path / "guidelines.md"),
        ),
        artifacts=ArtifactIndex(paper_full_tex=str(paper_path)),
    )
    save_session(tmp_path, state)
    set_current_session(tmp_path, state.session_id)
    return paper_path


def test_citation_integrity_facade_reexports_paths_and_gate_helpers() -> None:
    assert citation_integrity.CITATION_INTEGRITY_AUDIT_FILENAME == citation_integrity_paths.CITATION_INTEGRITY_AUDIT_FILENAME
    assert citation_integrity.citation_integrity_audit_path is citation_integrity_paths.citation_integrity_audit_path
    assert citation_integrity.citation_integrity_critic_path is citation_integrity_paths.citation_integrity_critic_path
    assert citation_integrity.citation_intent_plan_path is citation_integrity_paths.citation_intent_plan_path
    assert citation_integrity.citation_source_match_path is citation_integrity_paths.citation_source_match_path
    assert citation_integrity.build_citation_integrity_critic is citation_integrity_gate.build_citation_integrity_critic
    assert citation_integrity.write_citation_integrity_critic is citation_integrity_gate.write_citation_integrity_critic
    assert citation_integrity.citation_integrity_check is citation_integrity_gate.citation_integrity_check


def test_citation_integrity_check_allows_missing_artifacts_outside_claim_safe(tmp_path: Path) -> None:
    paper_path = _write_session(tmp_path)
    state = SimpleNamespace(artifacts=SimpleNamespace(paper_full_tex=str(paper_path)))

    payload = citation_integrity_gate.citation_integrity_check(tmp_path, state, quality_mode="ralph")

    assert payload["status"] == "pass"
    assert payload["failing_codes"] == []
    assert payload["mode_effect"] == "missing_artifacts_allowed_outside_claim_safe"


def test_citation_integrity_check_requires_artifacts_in_claim_safe_mode(tmp_path: Path) -> None:
    paper_path = _write_session(tmp_path)
    state = SimpleNamespace(artifacts=SimpleNamespace(paper_full_tex=str(paper_path)))

    payload = citation_integrity_gate.citation_integrity_check(tmp_path, state, quality_mode="claim_safe")

    assert payload["status"] == "fail"
    assert payload["failing_codes"] == [
        "citation_critic_missing",
        "citation_integrity_missing",
        "rendered_reference_audit_missing",
    ]
    assert payload["mode_effect"] == "hard_fail_in_claim_safe"


def test_build_citation_integrity_critic_reviews_bound_artifacts(tmp_path: Path) -> None:
    paper_path = _write_session(tmp_path)
    manuscript_sha = citation_integrity_gate._file_sha256(paper_path)
    for artifact_path in (
        citation_integrity_paths.rendered_reference_audit_path(tmp_path),
        citation_integrity_paths.citation_intent_plan_path(tmp_path),
        citation_integrity_paths.citation_source_match_path(tmp_path),
        citation_integrity_paths.citation_integrity_audit_path(tmp_path),
    ):
        _write_json(artifact_path, {"status": "pass", "manuscript_sha256": manuscript_sha})

    payload = citation_integrity_gate.build_citation_integrity_critic(tmp_path, quality_mode="claim_safe")

    assert payload["status"] == "pass"
    assert payload["schema_version"] == "citation-integrity-critic/1"
    assert payload["quality_mode"] == "claim_safe"
    assert payload["manuscript_sha256"] == manuscript_sha
    assert payload["failing_codes"] == []
    assert [item["name"] for item in payload["reviewed_artifacts"]] == [
        "rendered_reference_audit",
        "citation_intent_plan",
        "citation_source_match",
        "citation_integrity_audit",
    ]
