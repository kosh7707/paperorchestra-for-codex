from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paperorchestra.engine.review_stages import (
    compile_current_paper,
    record_current_validation_report,
    write_figure_placement_review,
)
from paperorchestra.loop_engine.quality.loop import write_quality_eval, write_quality_loop_plan
from paperorchestra.loop_engine.ralph.artifacts import _refresh_citation_integrity_for_current_manuscript
from paperorchestra.loop_engine.ralph.bridge_records import build_verification_record
from paperorchestra.loop_engine.ralph.state import _citation_summary, compute_progress_delta
from paperorchestra.reviews.citation_model_writer import write_citation_support_review
from paperorchestra.reviews.section_review import write_section_review
from paperorchestra.runtime.provider_base import BaseProvider


@dataclass(frozen=True)
class QaLoopPostActionVerification:
    validation_payload: dict[str, Any]
    compile_payload: dict[str, Any] | None
    after_eval_path: str | Path
    after_eval: dict[str, Any]
    after_plan_path: str | Path
    after_plan: dict[str, Any]
    after_summary: dict[str, Any]
    progress: dict[str, Any]
    verdict: str
    verification: dict[str, Any]


def verify_after_qa_loop_actions(
    *,
    cwd: str | Path | None,
    before_eval: dict[str, Any],
    before_summary: dict[str, Any],
    execution: dict[str, Any],
    citation_provider: BaseProvider,
    citation_evidence_mode: str,
    quality_mode: str,
    max_iterations: int,
    require_live_verification: bool,
    accept_mixed_provenance: bool,
    require_compile: bool,
) -> QaLoopPostActionVerification:
    validation_path, validation_payload = record_current_validation_report(cwd, name="validation.qa-loop-step.json")
    compile_payload: dict[str, Any] | None = None
    if require_compile:
        try:
            pdf_path = compile_current_paper(cwd)
            compile_payload = {"ok": True, "pdf": str(pdf_path)}
        except Exception as exc:
            compile_payload = {"ok": False, "error": str(exc)}
    section_review_path = write_section_review(cwd)
    figure_review_path, figure_review_payload = write_figure_placement_review(cwd)
    citation_review_path = write_citation_support_review(
        cwd,
        provider=citation_provider,
        evidence_mode=citation_evidence_mode,
    )
    refreshed_citation_integrity = _refresh_citation_integrity_for_current_manuscript(
        cwd,
        quality_mode=quality_mode,
    )
    after_eval_path, after_eval = write_quality_eval(
        cwd,
        require_live_verification=require_live_verification,
        quality_mode=quality_mode,
        max_iterations=max_iterations,
        current_attempt_consumes_budget=bool(execution["actions_attempted"]),
    )
    after_plan_path, after_plan = write_quality_loop_plan(
        cwd,
        require_live_verification=require_live_verification,
        quality_mode=quality_mode,
        max_iterations=max_iterations,
        accept_mixed_provenance=accept_mixed_provenance,
        quality_eval_input_path=after_eval_path,
    )
    after_summary = _citation_summary(cwd)
    progress = compute_progress_delta(before_eval, after_eval, before_summary, after_summary)
    verdict = str(after_plan.get("verdict"))
    verification = build_verification_record(
        validation_path=validation_path,
        validation_payload=validation_payload,
        compile_payload=compile_payload,
        section_review_path=section_review_path,
        figure_review_path=figure_review_path,
        figure_review_payload=figure_review_payload,
        citation_review_path=citation_review_path,
        refreshed_citation_integrity=refreshed_citation_integrity,
        quality_eval_path=after_eval_path,
        qa_loop_plan_path=after_plan_path,
    )
    return QaLoopPostActionVerification(
        validation_payload=validation_payload,
        compile_payload=compile_payload,
        after_eval_path=after_eval_path,
        after_eval=after_eval,
        after_plan_path=after_plan_path,
        after_plan=after_plan,
        after_summary=after_summary,
        progress=progress,
        verdict=verdict,
        verification=verification,
    )
