from __future__ import annotations

from pathlib import Path

from paperorchestra.core.models import utc_now_iso
from paperorchestra.loop_engine.quality.loop import DEFAULT_MAX_ITERATIONS
from paperorchestra.loop_engine.ralph.action_dispatch import dispatch_qa_loop_actions
from paperorchestra.loop_engine.ralph.action_dispatch_types import QaLoopActionDispatchContext
from paperorchestra.loop_engine.ralph.bridge_candidate_flow import resolve_post_dispatch_candidate
from paperorchestra.loop_engine.ralph.bridge_lifecycle import (
    finish_execution_error,
    finish_no_supported_actions,
    finish_successful_step,
    finish_terminal_noop,
    record_unsupported_actions,
)
from paperorchestra.loop_engine.ralph.bridge_post_action import verify_after_qa_loop_actions
from paperorchestra.loop_engine.ralph.bridge_preflight import prepare_qa_loop_preflight
from paperorchestra.loop_engine.ralph.bridge_rollback import (
    capture_qa_loop_rollback_context,
    restore_candidate_after_exception,
)
from paperorchestra.loop_engine.ralph.candidate_outcomes import should_override_no_progress
from paperorchestra.runtime.providers import BaseProvider, get_citation_support_provider
from .state import (
    TERMINAL_VERDICTS,
    StepResult,
    recover_pending_manuscript_write,
)


def run_qa_loop_step(
    cwd: str | Path | None,
    provider: BaseProvider,
    *,
    quality_mode: str = "claim_safe",
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    require_live_verification: bool = False,
    accept_mixed_provenance: bool = False,
    runtime_mode: str = "compatibility",
    require_compile: bool = False,
    citation_evidence_mode: str = "web",
    citation_provider_name: str | None = None,
    citation_provider_command: str | None = None,
    quality_eval_input_path: str | Path | None = None,
    qa_loop_plan_input_path: str | Path | None = None,
    citation_support_review_path: str | Path | None = None,
) -> StepResult:
    recover_pending_manuscript_write(cwd)
    preflight = prepare_qa_loop_preflight(
        cwd=cwd,
        started_at=utc_now_iso(),
        require_live_verification=require_live_verification,
        quality_mode=quality_mode,
        max_iterations=max_iterations,
        accept_mixed_provenance=accept_mixed_provenance,
        quality_eval_input_path=quality_eval_input_path,
        qa_loop_plan_input_path=qa_loop_plan_input_path,
        citation_support_review_path=citation_support_review_path,
    )
    execution = preflight.execution
    if preflight.initial_verdict in TERMINAL_VERDICTS:
        return finish_terminal_noop(cwd, execution, preflight.initial_verdict)

    record_unsupported_actions(execution, preflight.unsupported_actions)
    if not preflight.actions:
        return finish_no_supported_actions(cwd, execution)

    rollback = capture_qa_loop_rollback_context(cwd)
    citation_provider = get_citation_support_provider(
        citation_provider_name or ("shell" if citation_evidence_mode in {"web", "model"} else "mock"),
        command=citation_provider_command,
        evidence_mode=citation_evidence_mode,
    )
    dispatch_result = dispatch_qa_loop_actions(
        preflight.actions,
        execution,
        QaLoopActionDispatchContext(
            cwd=cwd,
            provider=provider,
            runtime_mode=runtime_mode,
            require_compile=require_compile,
            quality_mode=quality_mode,
            citation_evidence_mode=citation_evidence_mode,
            citation_provider=citation_provider,
            paper_path=rollback.paper_path,
            original_paper=rollback.original_paper,
        ),
    )

    try:
        post_action = verify_after_qa_loop_actions(
            cwd=cwd,
            before_eval=preflight.before_eval,
            before_summary=preflight.before_summary,
            execution=execution,
            citation_provider=citation_provider,
            citation_evidence_mode=citation_evidence_mode,
            quality_mode=quality_mode,
            max_iterations=max_iterations,
            require_live_verification=require_live_verification,
            accept_mixed_provenance=accept_mixed_provenance,
            require_compile=require_compile,
        )
        resolved = resolve_post_dispatch_candidate(
            cwd=cwd,
            rollback=rollback,
            require_compile=require_compile,
            require_live_verification=require_live_verification,
            quality_mode=quality_mode,
            max_iterations=max_iterations,
            accept_mixed_provenance=accept_mixed_provenance,
            before_eval=preflight.before_eval,
            before_summary=preflight.before_summary,
            actions_attempted=bool(execution["actions_attempted"]),
            citation_candidate_applied=dispatch_result.citation_candidate_applied,
            citation_candidate_path=dispatch_result.citation_candidate_path,
            post_action=post_action,
        )
        verdict = resolved.verdict
        execution.update(resolved.execution_updates)
        if should_override_no_progress(
            verdict=verdict,
            actions_attempted=execution["actions_attempted"],
            final_progress=resolved.final_progress,
            citation_candidate_applied=dispatch_result.citation_candidate_applied,
            candidate_progress=post_action.progress,
        ):
            verdict = "human_needed"
            execution["no_progress_override"] = True
    except Exception as exc:
        restore_candidate_after_exception(
            cwd=cwd,
            rollback=rollback,
            citation_candidate_applied=dispatch_result.citation_candidate_applied,
        )
        return finish_execution_error(
            cwd=cwd,
            execution=execution,
            before_eval=preflight.before_eval,
            before_plan_path=preflight.before_plan_path,
            before_eval_path=preflight.before_eval_path,
            error=exc,
            citation_candidate_applied=dispatch_result.citation_candidate_applied,
        )

    return finish_successful_step(
        cwd=cwd,
        execution=execution,
        final_eval=resolved.final_eval,
        final_eval_path=resolved.final_eval_path,
        final_plan_path=resolved.final_plan_path,
        final_summary=resolved.final_summary,
        final_progress=resolved.final_progress,
        final_verification=resolved.final_verification,
        verdict=verdict,
    )
