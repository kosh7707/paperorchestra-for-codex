from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paperorchestra.loop_engine.ralph.auto_commit import _auto_commit_progressive_citation_candidate
from paperorchestra.loop_engine.ralph.bridge_candidate_resolution import (
    CandidateResolutionRequest,
    PostActionState,
    resolve_candidate_outcome,
)
from paperorchestra.loop_engine.ralph.bridge_records import build_candidate_state
from paperorchestra.loop_engine.ralph.bridge_rollback import QaLoopRollbackContext
from paperorchestra.loop_engine.ralph.candidate_outcomes import classify_candidate_outcome
from paperorchestra.loop_engine.ralph.state import _failing_codes
from paperorchestra.loop_engine.ralph.bridge_post_action import QaLoopPostActionVerification


@dataclass(frozen=True)
class QaLoopResolvedPostAction:
    final_eval_path: str | Path
    final_eval: dict[str, Any]
    final_plan_path: str | Path
    final_summary: dict[str, Any]
    final_progress: dict[str, Any]
    final_verification: dict[str, Any]
    verdict: str
    execution_updates: dict[str, Any]


def resolve_post_dispatch_candidate(
    *,
    cwd: str | Path | None,
    rollback: QaLoopRollbackContext,
    require_compile: bool,
    require_live_verification: bool,
    quality_mode: str,
    max_iterations: int,
    accept_mixed_provenance: bool,
    before_eval: dict[str, Any],
    before_summary: dict[str, Any],
    actions_attempted: bool,
    citation_candidate_applied: bool,
    citation_candidate_path: str | None,
    post_action: QaLoopPostActionVerification,
) -> QaLoopResolvedPostAction:
    candidate_state: dict[str, Any] | None = None
    if citation_candidate_applied:
        candidate_state = build_candidate_state(
            manuscript_path=citation_candidate_path,
            verification=post_action.verification,
            after_eval=post_action.after_eval,
            after_summary=post_action.after_summary,
            quality_eval_path=post_action.after_eval_path,
            qa_loop_plan_path=post_action.after_plan_path,
            qa_loop_plan_verdict=post_action.verdict,
            progress=post_action.progress,
        )
    after_codes = set(_failing_codes(post_action.after_eval))
    residual_citation_failures = sorted(code for code in after_codes if code.startswith("citation_support_"))
    auto_commit_allowed, auto_commit_reason = (
        _auto_commit_progressive_citation_candidate(
            progress=post_action.progress,
            validation_payload=post_action.validation_payload,
            compile_payload=post_action.compile_payload,
            require_compile=require_compile,
            before_quality_eval=before_eval,
            after_quality_eval=post_action.after_eval,
            after_codes=after_codes,
            residual_citation_failures=residual_citation_failures,
        )
        if citation_candidate_applied
        else (False, "no_citation_candidate")
    )
    candidate_outcome = classify_candidate_outcome(
        citation_candidate_applied=citation_candidate_applied,
        auto_commit_allowed=auto_commit_allowed,
        after_codes=after_codes,
    )
    resolution = resolve_candidate_outcome(
        CandidateResolutionRequest(
            cwd=cwd,
            paper_path=rollback.paper_path,
            original_paper=rollback.original_paper,
            mutation_snapshot=rollback.mutation_snapshot,
            citation_review_snapshot=rollback.citation_review_snapshot,
            citation_trace_snapshot=rollback.citation_trace_snapshot,
            require_compile=require_compile,
            require_live_verification=require_live_verification,
            quality_mode=quality_mode,
            max_iterations=max_iterations,
            accept_mixed_provenance=accept_mixed_provenance,
            before_eval=before_eval,
            before_summary=before_summary,
            actions_attempted=actions_attempted,
            candidate_outcome=candidate_outcome,
            candidate_path=citation_candidate_path,
            candidate_state=candidate_state,
            candidate_progress=post_action.progress,
            auto_commit_reason=auto_commit_reason,
            residual_citation_failures=residual_citation_failures,
            after_codes=after_codes,
        ),
        PostActionState(
            eval_path=post_action.after_eval_path,
            eval_payload=post_action.after_eval,
            plan_path=post_action.after_plan_path,
            plan_payload=post_action.after_plan,
            summary=post_action.after_summary,
            progress=post_action.progress,
            verification=post_action.verification,
            verdict=post_action.verdict,
        ),
    )
    return QaLoopResolvedPostAction(
        final_eval_path=resolution.final_eval_path,
        final_eval=resolution.final_eval,
        final_plan_path=resolution.final_plan_path,
        final_summary=resolution.final_summary,
        final_progress=resolution.final_progress,
        final_verification=resolution.final_verification,
        verdict=resolution.verdict,
        execution_updates=resolution.execution_updates,
    )
