from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.models import utc_now_iso
from paperorchestra.engine.pipeline import (
    compile_current_paper,
    record_current_validation_report,
    write_figure_placement_review,
)
from paperorchestra.reviews.critics import write_citation_support_review, write_section_review
from paperorchestra.runtime.providers import BaseProvider, get_citation_support_provider
from ..quality.loop import (
    DEFAULT_MAX_ITERATIONS,
    QA_LOOP_SUPPORTED_HANDLER_CODES,
    append_quality_loop_history,
    build_quality_loop_plan,
    write_quality_eval,
    write_quality_loop_plan,
)
from paperorchestra.core.session import load_session
from paperorchestra.loop_engine.ralph.bridge_actions import (
    _executable_actions,
    _unsupported_executable_actions,
)
from paperorchestra.loop_engine.ralph.bridge_restore import _restore_current_after_uncommitted_candidate
from paperorchestra.loop_engine.ralph.candidate_outcomes import (
    build_auto_commit_record,
    build_auto_commit_rejection_records,
    build_citation_support_rejection_records,
    classify_candidate_outcome,
    should_override_no_progress,
)
from .handoff import (
    build_qa_loop_brief,
    build_ralph_start_payload,
    launch_omx_ralph,
    write_qa_loop_brief,
)
from .inputs import (
    _load_explicit_qa_loop_plan,
    _load_explicit_quality_eval,
    _quality_eval_path_from_plan,
    _stage_explicit_citation_support_review,
    _validate_plan_quality_eval_identity,
)
from .bridge_records import (
    build_candidate_state,
    build_initial_execution_record,
    build_restored_current_state,
    build_verification_record,
)
from .action_dispatch import QaLoopActionDispatchContext, dispatch_qa_loop_actions
from .artifacts import (
    _refresh_citation_integrity_for_current_manuscript,
    _write_execution_artifact,
)
from .auto_commit import _auto_commit_progressive_citation_candidate
from .state import (
    EXIT_CODES,
    OMX_TMUX_INJECT_MARKER,
    OMX_TMUX_INJECT_PROMPT,
    QA_LOOP_BRIEF_FILENAME,
    QA_LOOP_EXECUTION_SCHEMA_VERSION,
    QA_LOOP_HANDOFF_FILENAME,
    SUPPORTED_HANDLER_CODES,
    TERMINAL_VERDICTS,
    StepResult,
    atomic_write_text,
    _citation_issue_count,
    _citation_summary,
    _file_content_snapshot,
    _failing_codes,
    _next_execution_path,
    _plan_path,
    _qa_loop_step_command,
    _restore_file_content_snapshot,
    _restore_session_mutation_snapshot,
    _session_mutation_snapshot,
    clear_pending_manuscript_write,
    compute_progress_delta,
    qa_loop_exit_code,
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
    started = utc_now_iso()
    explicit_citation_support_path = _stage_explicit_citation_support_review(cwd, citation_support_review_path)
    if qa_loop_plan_input_path:
        before_plan_path = Path(qa_loop_plan_input_path).resolve()
        before_plan = _load_explicit_qa_loop_plan(cwd, before_plan_path)
        quality_eval_input_path = quality_eval_input_path or _quality_eval_path_from_plan(before_plan)
        if not quality_eval_input_path:
            raise ValueError(f"qa-loop-plan input does not identify a quality-eval artifact: {before_plan_path}")
        before_eval_path, before_eval = _load_explicit_quality_eval(cwd, quality_eval_input_path)
        _validate_plan_quality_eval_identity(before_plan, before_eval_path)
    else:
        if quality_eval_input_path:
            before_eval_path, before_eval = _load_explicit_quality_eval(cwd, quality_eval_input_path)
        else:
            before_eval_path, before_eval = write_quality_eval(
                cwd,
                require_live_verification=require_live_verification,
                quality_mode=quality_mode,
                max_iterations=max_iterations,
            )
        before_plan_path, before_plan = write_quality_loop_plan(
            cwd,
            require_live_verification=require_live_verification,
            quality_mode=quality_mode,
            max_iterations=max_iterations,
            accept_mixed_provenance=accept_mixed_provenance,
            quality_eval_input_path=before_eval_path,
        )
    before_summary = _citation_summary(cwd)
    initial_verdict = str(before_plan.get("verdict"))
    execution = build_initial_execution_record(
        cwd=cwd,
        started_at=started,
        before_eval_path=before_eval_path,
        before_plan_path=before_plan_path,
        explicit_citation_support_path=explicit_citation_support_path,
        before_eval=before_eval,
        before_summary=before_summary,
    )
    actions = _executable_actions(before_plan)
    if initial_verdict in TERMINAL_VERDICTS:
        execution.update({"completed_at": utc_now_iso(), "verdict": initial_verdict, "terminal_noop": True})
        path = _write_execution_artifact(cwd, execution)
        return StepResult(path=path, payload=execution, exit_code=qa_loop_exit_code(initial_verdict))
    unsupported_actions = _unsupported_executable_actions(before_plan)
    for action in unsupported_actions:
        execution["actions_skipped"].append({"code": action.get("code"), "reason": "unsupported_handler"})

    if not actions:
        execution.update(
            {
                "completed_at": utc_now_iso(),
                "verdict": "human_needed",
                "reason": "no_supported_executable_handlers",
            }
        )
        path = _write_execution_artifact(cwd, execution)
        return StepResult(path=path, payload=execution, exit_code=qa_loop_exit_code("human_needed"))

    state_for_rollback = load_session(cwd)
    paper_path = (
        Path(state_for_rollback.artifacts.paper_full_tex)
        if state_for_rollback.artifacts.paper_full_tex
        else None
    )
    original_paper = paper_path.read_text(encoding="utf-8") if paper_path and paper_path.exists() else None
    mutation_snapshot = _session_mutation_snapshot(state_for_rollback)
    citation_review_snapshot = _file_content_snapshot(
        paper_path.resolve().parent / "citation_support_review.json" if paper_path else None
    )
    citation_trace_snapshot = _file_content_snapshot(
        paper_path.resolve().parent / "citation_support_review.trace.json" if paper_path else None
    )
    citation_provider = get_citation_support_provider(
        citation_provider_name or ("shell" if citation_evidence_mode in {"web", "model"} else "mock"),
        command=citation_provider_command,
        evidence_mode=citation_evidence_mode,
    )
    dispatch_result = dispatch_qa_loop_actions(
        actions,
        execution,
        QaLoopActionDispatchContext(
            cwd=cwd,
            provider=provider,
            runtime_mode=runtime_mode,
            require_compile=require_compile,
            quality_mode=quality_mode,
            citation_evidence_mode=citation_evidence_mode,
            citation_provider=citation_provider,
            paper_path=paper_path,
            original_paper=original_paper,
        ),
    )
    citation_candidate_applied = dispatch_result.citation_candidate_applied
    citation_candidate_path = dispatch_result.citation_candidate_path

    try:
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
        candidate_state: dict[str, Any] | None = None
        if citation_candidate_applied:
            candidate_state = build_candidate_state(
                manuscript_path=citation_candidate_path,
                verification=verification,
                after_eval=after_eval,
                after_summary=after_summary,
                quality_eval_path=after_eval_path,
                qa_loop_plan_path=after_plan_path,
                qa_loop_plan_verdict=verdict,
                progress=progress,
            )
        final_eval = after_eval
        final_plan = after_plan
        final_eval_path = after_eval_path
        final_plan_path = after_plan_path
        final_summary = after_summary
        final_progress = progress
        final_verification = verification
        after_codes = set(_failing_codes(after_eval))
        residual_citation_failures = sorted(code for code in after_codes if code.startswith("citation_support_"))
        auto_commit_allowed, auto_commit_reason = (
            _auto_commit_progressive_citation_candidate(
                progress=progress,
                validation_payload=validation_payload,
                compile_payload=compile_payload,
                require_compile=require_compile,
                before_quality_eval=before_eval,
                after_quality_eval=after_eval,
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
        if candidate_outcome == "auto_commit":
            clear_pending_manuscript_write(
                cwd,
                status="resolved",
                reason="qa_loop_progressive_citation_candidate_committed",
            )
            execution["candidate_state"] = candidate_state
            execution["candidate_progress"] = progress
            execution["candidate_auto_commit"] = build_auto_commit_record(
                candidate_path=citation_candidate_path,
                auto_commit_reason=auto_commit_reason,
                residual_citation_failures=residual_citation_failures,
                after_codes=after_codes,
            )
        elif candidate_outcome == "citation_support_rejected":
            restored = _restore_current_after_uncommitted_candidate(
                cwd,
                paper_path=paper_path,
                original_paper=original_paper,
                mutation_snapshot=mutation_snapshot,
                citation_review_snapshot=citation_review_snapshot,
                citation_trace_snapshot=citation_trace_snapshot,
                require_compile=require_compile,
                require_live_verification=require_live_verification,
                quality_mode=quality_mode,
                max_iterations=max_iterations,
                accept_mixed_provenance=accept_mixed_provenance,
                before_eval=before_eval,
                before_summary=before_summary,
                actions_attempted=bool(execution["actions_attempted"]),
                validation_name="validation.qa-loop-step.rollback.json",
            )
            if restored:
                final_eval_path = restored["quality_eval_path"]
                final_eval = restored["quality_eval"]
                final_plan_path = restored["qa_loop_plan_path"]
                final_plan = restored["qa_loop_plan"]
                final_summary = restored["citation_summary"]
                final_progress = restored["progress"]
                final_verification = restored["verification"]
                execution["restored_current_verification"] = restored["verification"]
                execution["restored_current_state"] = build_restored_current_state(
                    verification=restored["verification"],
                    final_eval=final_eval,
                    final_summary=final_summary,
                    quality_eval_path=final_eval_path,
                    qa_loop_plan_path=final_plan_path,
                    qa_loop_plan_verdict=str(final_plan.get("verdict")),
                    progress=final_progress,
                )
            verdict = "human_needed"
            rejection = build_citation_support_rejection_records(
                candidate_path=citation_candidate_path,
                residual_citation_failures=residual_citation_failures,
                auto_commit_reason=auto_commit_reason,
            )
            execution["candidate_rollback"] = rejection["rollback"]
            execution["candidate_state"] = candidate_state
            execution["candidate_progress"] = progress
            execution["candidate_handoff"] = rejection["handoff"]
        elif candidate_outcome == "auto_commit_gate_rejected":
            restored = _restore_current_after_uncommitted_candidate(
                cwd,
                paper_path=paper_path,
                original_paper=original_paper,
                mutation_snapshot=mutation_snapshot,
                citation_review_snapshot=citation_review_snapshot,
                citation_trace_snapshot=citation_trace_snapshot,
                require_compile=require_compile,
                require_live_verification=require_live_verification,
                quality_mode=quality_mode,
                max_iterations=max_iterations,
                accept_mixed_provenance=accept_mixed_provenance,
                before_eval=before_eval,
                before_summary=before_summary,
                actions_attempted=bool(execution["actions_attempted"]),
                validation_name="validation.qa-loop-step.candidate-approved-original-restored.json",
            )
            if restored:
                final_eval_path = restored["quality_eval_path"]
                final_eval = restored["quality_eval"]
                final_plan_path = restored["qa_loop_plan_path"]
                final_plan = restored["qa_loop_plan"]
                final_summary = restored["citation_summary"]
                final_progress = restored["progress"]
                final_verification = restored["verification"]
                execution["restored_current_verification"] = restored["verification"]
                execution["restored_current_state"] = build_restored_current_state(
                    verification=restored["verification"],
                    final_eval=final_eval,
                    final_summary=final_summary,
                    quality_eval_path=final_eval_path,
                    qa_loop_plan_path=final_plan_path,
                    qa_loop_plan_verdict=str(final_plan.get("verdict")),
                    progress=final_progress,
                )
            verdict = "human_needed"
            rejection = build_auto_commit_rejection_records(
                candidate_path=citation_candidate_path,
                auto_commit_reason=auto_commit_reason,
                after_codes=after_codes,
            )
            execution["candidate_rollback"] = rejection["rollback"]
            execution["candidate_handoff"] = rejection["handoff"]
            execution["candidate_state"] = candidate_state
            execution["candidate_progress"] = progress
        if should_override_no_progress(
            verdict=verdict,
            actions_attempted=execution["actions_attempted"],
            final_progress=final_progress,
            citation_candidate_applied=citation_candidate_applied,
            candidate_progress=progress,
        ):
            verdict = "human_needed"
            execution["no_progress_override"] = True
    except Exception as exc:
        if citation_candidate_applied and paper_path and original_paper is not None:
            atomic_write_text(paper_path, original_paper)
            clear_pending_manuscript_write(cwd, status="restored", reason="qa_loop_candidate_exception")
            _restore_session_mutation_snapshot(cwd, mutation_snapshot)
        execution.update(
            {
                "completed_at": utc_now_iso(),
                "verdict": "execution_error",
                "error": str(exc),
                "candidate_rollback": {"reason": "exception"} if citation_candidate_applied else None,
            }
        )
        path = _write_execution_artifact(cwd, execution)
        if execution["actions_attempted"]:
            append_quality_loop_history(
                cwd,
                before_eval,
                verdict="execution_error",
                plan_path=before_plan_path,
                quality_eval_path=before_eval_path,
                execution_path=path,
                event_type="qa_loop_step",
                consumes_budget=True,
            )
        return StepResult(path=path, payload=execution, exit_code=qa_loop_exit_code("execution_error"))
    execution.update(
        {
            "completed_at": utc_now_iso(),
            "verification": final_verification,
            "after": {"failing_codes": _failing_codes(final_eval), "citation_support_summary": final_summary},
            "progress": final_progress,
            "verdict": verdict,
        }
    )
    path = _write_execution_artifact(cwd, execution)
    if execution["actions_attempted"]:
        append_quality_loop_history(
            cwd,
            final_eval,
            verdict=verdict,
            plan_path=final_plan_path,
            quality_eval_path=final_eval_path,
            execution_path=path,
            event_type="qa_loop_step",
            consumes_budget=True,
            extra=(
                {"actionable_failure": execution.get("actionable_failure")}
                if execution.get("actionable_failure")
                else None
            ),
        )
    return StepResult(path=path, payload=execution, exit_code=qa_loop_exit_code(verdict))
