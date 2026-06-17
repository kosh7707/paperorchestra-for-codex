from __future__ import annotations

from pathlib import Path

from paperorchestra.loop_engine.ralph.bridge_records import (
    build_candidate_state,
    build_initial_execution_record,
    build_restored_current_state,
    build_verification_record,
)


def test_build_initial_execution_record_preserves_inputs_and_before_snapshot() -> None:
    execution = build_initial_execution_record(
        cwd=None,
        started_at="2026-06-18T00:00:00Z",
        before_eval_path=Path("/tmp/quality.json"),
        before_plan_path=Path("/tmp/plan.json"),
        explicit_citation_support_path=Path("/tmp/citation.json"),
        before_eval={"tiers": {"tier_1": {"status": "fail", "failing_codes": ["missing"]}}},
        before_summary={"issue_count": 3},
    )

    assert execution["schema_version"] == "qa-loop-execution/1"
    assert execution["started_at"] == "2026-06-18T00:00:00Z"
    assert execution["input_quality_eval"] == "/tmp/quality.json"
    assert execution["input_plan"] == "/tmp/plan.json"
    assert execution["input_citation_support_review"] == "/tmp/citation.json"
    assert execution["input_artifacts"] == {
        "quality_eval": "/tmp/quality.json",
        "qa_loop_plan": "/tmp/plan.json",
        "citation_support_review": "/tmp/citation.json",
    }
    assert execution["actions_attempted"] == []
    assert execution["actions_skipped"] == []
    assert execution["before"] == {
        "failing_codes": ["missing"],
        "citation_support_summary": {"issue_count": 3},
    }


def test_build_verification_record_keeps_artifact_paths_and_optional_compile() -> None:
    record = build_verification_record(
        validation_path=Path("/tmp/validation.json"),
        validation_payload={"ok": True},
        compile_payload=None,
        section_review_path=Path("/tmp/sections.json"),
        figure_review_path=Path("/tmp/figures.json"),
        figure_review_payload={"manuscript_sha256": "sha256:fig"},
        citation_review_path=Path("/tmp/citations.json"),
        refreshed_citation_integrity={"status": "ok"},
        quality_eval_path=Path("/tmp/quality.after.json"),
        qa_loop_plan_path=Path("/tmp/plan.after.json"),
    )

    assert record == {
        "validate_current": {"path": "/tmp/validation.json", "ok": True},
        "compile": None,
        "section_review": {"path": "/tmp/sections.json"},
        "figure_placement_review": {"path": "/tmp/figures.json", "manuscript_sha256": "sha256:fig"},
        "citation_support_review": {"path": "/tmp/citations.json"},
        "citation_integrity": {"status": "ok"},
        "quality_eval": {"path": "/tmp/quality.after.json"},
        "qa_loop_plan": {"path": "/tmp/plan.after.json"},
    }


def test_candidate_and_restored_state_records_share_verification_shape() -> None:
    verification = {"quality_eval": {"path": "/tmp/quality.after.json"}}
    candidate = build_candidate_state(
        manuscript_path="/tmp/candidate.tex",
        verification=verification,
        after_eval={"tiers": {}},
        after_summary={"issue_count": 0},
        quality_eval_path=Path("/tmp/quality.after.json"),
        qa_loop_plan_path=Path("/tmp/plan.after.json"),
        qa_loop_plan_verdict="continue",
        progress={"forward_progress": True},
    )
    restored = build_restored_current_state(
        verification=verification,
        final_eval={"tiers": {"tier_1": {"status": "fail", "failing_codes": ["remaining"]}}},
        final_summary={"issue_count": 1},
        quality_eval_path=Path("/tmp/quality.restored.json"),
        qa_loop_plan_path=Path("/tmp/plan.restored.json"),
        qa_loop_plan_verdict="human_needed",
        progress={"forward_progress": False},
    )

    assert candidate["manuscript_path"] == "/tmp/candidate.tex"
    assert candidate["verification"] is verification
    assert candidate["after"] == {"failing_codes": [], "citation_support_summary": {"issue_count": 0}}
    assert candidate["quality_eval_path"] == "/tmp/quality.after.json"
    assert candidate["qa_loop_plan_verdict"] == "continue"
    assert restored["verification"] is verification
    assert restored["after"] == {
        "failing_codes": ["remaining"],
        "citation_support_summary": {"issue_count": 1},
    }
    assert restored["quality_eval_path"] == "/tmp/quality.restored.json"
    assert restored["qa_loop_plan_verdict"] == "human_needed"
