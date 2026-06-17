from __future__ import annotations

from pathlib import Path
from typing import Any

from .state import QA_LOOP_EXECUTION_SCHEMA_VERSION, _failing_codes, _next_execution_path


def build_initial_execution_record(
    *,
    cwd: str | Path | None,
    started_at: str,
    before_eval_path: str | Path,
    before_plan_path: str | Path,
    explicit_citation_support_path: str | Path | None,
    before_eval: dict[str, Any],
    before_summary: dict[str, Any],
) -> dict[str, Any]:
    citation_path = str(explicit_citation_support_path) if explicit_citation_support_path else None
    return {
        "schema_version": QA_LOOP_EXECUTION_SCHEMA_VERSION,
        "started_at": started_at,
        "_reserved_execution_path": str(_next_execution_path(cwd)[1]),
        "input_quality_eval": str(before_eval_path),
        "input_plan": str(before_plan_path),
        "input_citation_support_review": citation_path,
        "input_artifacts": {
            "quality_eval": str(before_eval_path),
            "qa_loop_plan": str(before_plan_path),
            "citation_support_review": citation_path,
        },
        "actions_attempted": [],
        "actions_skipped": [],
        "before": {"failing_codes": _failing_codes(before_eval), "citation_support_summary": before_summary},
    }


def build_verification_record(
    *,
    validation_path: str | Path,
    validation_payload: dict[str, Any],
    compile_payload: dict[str, Any] | None,
    section_review_path: str | Path,
    figure_review_path: str | Path,
    figure_review_payload: dict[str, Any] | None,
    citation_review_path: str | Path,
    refreshed_citation_integrity: dict[str, Any],
    quality_eval_path: str | Path,
    qa_loop_plan_path: str | Path,
) -> dict[str, Any]:
    return {
        "validate_current": {"path": str(validation_path), "ok": validation_payload.get("ok")},
        "compile": compile_payload,
        "section_review": {"path": str(section_review_path)},
        "figure_placement_review": {
            "path": str(figure_review_path),
            "manuscript_sha256": figure_review_payload.get("manuscript_sha256")
            if isinstance(figure_review_payload, dict)
            else None,
        },
        "citation_support_review": {"path": str(citation_review_path)},
        "citation_integrity": refreshed_citation_integrity,
        "quality_eval": {"path": str(quality_eval_path)},
        "qa_loop_plan": {"path": str(qa_loop_plan_path)},
    }


def build_candidate_state(
    *,
    manuscript_path: str | None,
    verification: dict[str, Any],
    after_eval: dict[str, Any],
    after_summary: dict[str, Any],
    quality_eval_path: str | Path,
    qa_loop_plan_path: str | Path,
    qa_loop_plan_verdict: str,
    progress: dict[str, Any],
) -> dict[str, Any]:
    return {
        "manuscript_path": manuscript_path,
        "verification": verification,
        "after": {"failing_codes": _failing_codes(after_eval), "citation_support_summary": after_summary},
        "quality_eval_path": str(quality_eval_path),
        "qa_loop_plan_path": str(qa_loop_plan_path),
        "qa_loop_plan_verdict": qa_loop_plan_verdict,
        "progress": progress,
    }


def build_restored_current_state(
    *,
    verification: dict[str, Any],
    final_eval: dict[str, Any],
    final_summary: dict[str, Any],
    quality_eval_path: str | Path,
    qa_loop_plan_path: str | Path,
    qa_loop_plan_verdict: str,
    progress: dict[str, Any],
) -> dict[str, Any]:
    return {
        "verification": verification,
        "after": {"failing_codes": _failing_codes(final_eval), "citation_support_summary": final_summary},
        "quality_eval_path": str(quality_eval_path),
        "qa_loop_plan_path": str(qa_loop_plan_path),
        "qa_loop_plan_verdict": qa_loop_plan_verdict,
        "progress": progress,
    }


def build_restored_bridge_update(restored: dict[str, Any]) -> dict[str, Any]:
    final_eval_path = restored["quality_eval_path"]
    final_eval = restored["quality_eval"]
    final_plan_path = restored["qa_loop_plan_path"]
    final_plan = restored["qa_loop_plan"]
    final_summary = restored["citation_summary"]
    final_progress = restored["progress"]
    final_verification = restored["verification"]
    return {
        "final_eval_path": final_eval_path,
        "final_eval": final_eval,
        "final_plan_path": final_plan_path,
        "final_plan": final_plan,
        "final_summary": final_summary,
        "final_progress": final_progress,
        "final_verification": final_verification,
        "execution_updates": {
            "restored_current_verification": final_verification,
            "restored_current_state": build_restored_current_state(
                verification=final_verification,
                final_eval=final_eval,
                final_summary=final_summary,
                quality_eval_path=final_eval_path,
                qa_loop_plan_path=final_plan_path,
                qa_loop_plan_verdict=str(final_plan.get("verdict")),
                progress=final_progress,
            ),
        },
    }
