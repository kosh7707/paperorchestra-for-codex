from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.engine import refine_iteration_outcomes as outcomes
from paperorchestra.engine.refine_iteration_assessment import write_and_assess_refinement_candidate
from paperorchestra.engine.refine_iteration_types import (
    PreparedRefinementDraft,
    RefinementCandidateAssessment,
    RefinementIterationRun,
    RefinementReviewDecision,
)
from paperorchestra.engine.refine_iteration_prepare import prepare_refinement_draft
from paperorchestra.engine.refine_retry import maybe_retry_refinement_review
from paperorchestra.engine.refine_review import should_accept_refinement_candidate
from paperorchestra.runtime.provider_base import BaseProvider


def _review_refinement_decision(
    *,
    cwd: str | Path | None,
    provider: BaseProvider,
    runtime_mode: str,
    iteration: Any,
    assessment: RefinementCandidateAssessment,
) -> RefinementReviewDecision:
    accept = should_accept_refinement_candidate(
        compile_error=assessment.compile_error,
        no_op_refinement=assessment.no_op_refinement,
        candidate_score=assessment.candidate_score,
        previous_score=assessment.previous_score,
        candidate_axes=assessment.candidate_axes,
        previous_axes=assessment.previous_axes,
    )
    retry_review = maybe_retry_refinement_review(
        cwd=cwd,
        provider=provider,
        runtime_mode=runtime_mode,
        candidate_iter=iteration.candidate_iter,
        accept=accept,
        no_op_refinement=assessment.no_op_refinement,
        compile_error=assessment.compile_error,
        previous_score=assessment.previous_score,
        candidate_score=assessment.candidate_score,
        previous_axes=assessment.previous_axes,
        candidate_review_path=assessment.candidate_review_path,
    )
    return RefinementReviewDecision(
        accept=retry_review.accept,
        candidate_review_path=retry_review.candidate_review_path,
        candidate_score=retry_review.candidate_score,
        review_retry_paths=retry_review.review_retry_paths,
        review_retry_scores=retry_review.review_retry_scores,
    )


def run_refinement_iteration(
    *,
    cwd: str | Path | None,
    provider: BaseProvider,
    runtime_mode: str,
    require_compile_for_accept: bool,
    candidate_only: bool,
    claim_safe: bool,
    narrative_plan: dict[str, Any],
    claim_map: dict[str, Any],
    citation_placement_plan: dict[str, Any],
    writer_brief: dict[str, Any],
) -> RefinementIterationRun:
    draft = prepare_refinement_draft(
        cwd=cwd,
        provider=provider,
        runtime_mode=runtime_mode,
        claim_safe=claim_safe,
        narrative_plan=narrative_plan,
        claim_map=claim_map,
        citation_placement_plan=citation_placement_plan,
        writer_brief=writer_brief,
    )
    validation_name = f"validation.refine.iter-{draft.state.refinement_iteration + 1:02d}.json"
    validation_outcome = outcomes.record_refinement_validation_outcome(
        cwd=cwd,
        state=draft.state,
        iteration=draft.iteration,
        validation_issues=draft.validation_issues,
        validation_name=validation_name,
        latex=draft.latex,
    )
    if validation_outcome.failure_run is not None:
        return validation_outcome.failure_run

    assessment = write_and_assess_refinement_candidate(
        cwd=cwd,
        provider=provider,
        runtime_mode=runtime_mode,
        require_compile_for_accept=require_compile_for_accept,
        draft=draft,
        validation_path=validation_outcome.validation_path,
        validation_payload=validation_outcome.validation_payload,
    )
    if candidate_only:
        return outcomes.candidate_only_iteration_run(
            cwd=cwd,
            iteration=draft.iteration,
            assessment=assessment,
            contract_regression_preservation=draft.contract_regression_preservation,
        )

    decision = _review_refinement_decision(
        cwd=cwd,
        provider=provider,
        runtime_mode=runtime_mode,
        iteration=draft.iteration,
        assessment=assessment,
    )
    if decision.accept:
        return outcomes.accepted_iteration_run(cwd=cwd, draft=draft, assessment=assessment, decision=decision)
    return outcomes.rejected_iteration_run(cwd=cwd, draft=draft, assessment=assessment, decision=decision)


__all__ = [
    "PreparedRefinementDraft",
    "RefinementCandidateAssessment",
    "RefinementIterationRun",
    "RefinementReviewDecision",
    "run_refinement_iteration",
]
