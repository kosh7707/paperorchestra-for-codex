from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.engine.pipeline import compile_current_paper, record_current_validation_report, write_figure_placement_review
from paperorchestra.loop_engine.quality.loop import write_quality_eval, write_quality_loop_plan
from paperorchestra.loop_engine.ralph.artifacts import _refresh_citation_integrity_for_current_manuscript
from paperorchestra.loop_engine.ralph.state import (
    atomic_write_text,
    clear_pending_manuscript_write,
    _citation_summary,
    _failing_codes,
    _restore_file_content_snapshot,
    _restore_session_mutation_snapshot,
    compute_progress_delta,
)


def _restore_current_after_uncommitted_candidate(
    cwd: str | Path | None,
    *,
    paper_path: Path | None,
    original_paper: str | None,
    mutation_snapshot: dict[str, Any],
    citation_review_snapshot: dict[str, Any],
    citation_trace_snapshot: dict[str, Any],
    require_compile: bool,
    require_live_verification: bool,
    quality_mode: str,
    max_iterations: int,
    accept_mixed_provenance: bool,
    before_eval: dict[str, Any],
    before_summary: dict[str, int],
    actions_attempted: bool,
    validation_name: str,
) -> dict[str, Any] | None:
    if paper_path is None or original_paper is None:
        return None
    atomic_write_text(paper_path, original_paper)
    clear_pending_manuscript_write(cwd, status="restored", reason="uncommitted_candidate_restored")
    _restore_session_mutation_snapshot(cwd, mutation_snapshot)
    _restore_file_content_snapshot(citation_review_snapshot)
    _restore_file_content_snapshot(citation_trace_snapshot)
    restored_validation_path, restored_validation_payload = record_current_validation_report(cwd, name=validation_name)
    restored_compile_payload: dict[str, Any] | None = None
    if require_compile:
        try:
            restored_pdf_path = compile_current_paper(cwd)
            restored_compile_payload = {"ok": True, "pdf": str(restored_pdf_path)}
        except Exception as exc:
            restored_compile_payload = {"ok": False, "error": str(exc)}
    restored_figure_path, restored_figure_payload = write_figure_placement_review(cwd)
    refreshed_citation_integrity = _refresh_citation_integrity_for_current_manuscript(
        cwd,
        quality_mode=quality_mode,
    )
    final_eval_path, final_eval = write_quality_eval(
        cwd,
        require_live_verification=require_live_verification,
        quality_mode=quality_mode,
        max_iterations=max_iterations,
        current_attempt_consumes_budget=actions_attempted,
    )
    final_plan_path, final_plan = write_quality_loop_plan(
        cwd,
        require_live_verification=require_live_verification,
        quality_mode=quality_mode,
        max_iterations=max_iterations,
        accept_mixed_provenance=accept_mixed_provenance,
        quality_eval_input_path=final_eval_path,
    )
    final_summary = _citation_summary(cwd)
    final_progress = compute_progress_delta(before_eval, final_eval, before_summary, final_summary)
    return {
        "verification": {
            "validate_current": {"path": str(restored_validation_path), "ok": restored_validation_payload.get("ok")},
            "compile": restored_compile_payload,
            "figure_placement_review": {
                "path": str(restored_figure_path),
                "manuscript_sha256": restored_figure_payload.get("manuscript_sha256")
                if isinstance(restored_figure_payload, dict)
                else None,
            },
            "citation_integrity": refreshed_citation_integrity,
            "quality_eval": {"path": str(final_eval_path)},
            "qa_loop_plan": {"path": str(final_plan_path)},
            "citation_support_review_restored": {"path": citation_review_snapshot.get("path"), "restored": True},
            "citation_support_trace_restored": {"path": citation_trace_snapshot.get("path"), "restored": True},
        },
        "quality_eval_path": final_eval_path,
        "quality_eval": final_eval,
        "qa_loop_plan_path": final_plan_path,
        "qa_loop_plan": final_plan,
        "citation_summary": final_summary,
        "progress": final_progress,
    }
