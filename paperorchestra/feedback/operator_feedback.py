from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.runtime.providers import BaseProvider
from paperorchestra.feedback.operator_candidates import (
    _promote_candidate_text,
)
from paperorchestra.feedback.operator_verification import _verification_block, _verification_snapshot
from paperorchestra.feedback.operator_snapshots import _restore_session_snapshot, _session_snapshot
from paperorchestra.feedback.operator_contexts.citations import _protected_supported_citation_regressions
from paperorchestra.feedback.operator_feedback_attempts import prepare_operator_candidate_attempt
from paperorchestra.feedback.operator_feedback_evaluation import evaluate_operator_candidate_attempt
from paperorchestra.feedback.operator_feedback_rollback import rollback_operator_feedback_candidate
from paperorchestra.feedback.operator_feedback_context import load_operator_feedback_context, operator_feedback_attempt_count
from paperorchestra.feedback.operator_feedback_finalization import finalize_operator_feedback_execution
from paperorchestra.feedback.operator_feedback_exception import handle_operator_feedback_exception
from paperorchestra.core.errors import ContractError


def apply_operator_feedback(
    cwd: str | Path | None,
    provider: BaseProvider,
    *,
    imported_feedback_path: str | Path,
    max_supervised_iterations: int = 1,
    require_compile: bool = False,
    quality_mode: str = "claim_safe",
    max_iterations: int = 10,
    require_live_verification: bool = False,
    accept_mixed_provenance: bool = False,
    runtime_mode: str = "compatibility",
    citation_evidence_mode: str = "web",
    citation_provider_name: str | None = None,
    citation_provider_command: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    if max_supervised_iterations < 1:
        raise ContractError("max_supervised_iterations must be >= 1")
    context = load_operator_feedback_context(
        cwd=cwd,
        imported_feedback_path=imported_feedback_path,
        max_supervised_iterations=max_supervised_iterations,
    )
    imported = context.imported
    packet = context.packet
    intent = context.intent
    current_sha = context.current_sha
    base_quality_eval = context.base_quality_eval
    packet_prior_attempts = context.packet_prior_attempts
    base_tier2_failures = context.base_tier2_failures
    base_active_failures = context.base_active_failures
    execution = context.execution
    snapshot = _session_snapshot(cwd)
    before_text = snapshot.get("paper_text") or ""
    owner_categories = context.owner_categories
    final_incorporation: list[dict[str, Any]] = []
    final_verification: dict[str, Any] | None = None
    final_candidate_result: dict[str, Any] | None = None

    try:
        attempts = operator_feedback_attempt_count(intent=intent, max_supervised_iterations=max_supervised_iterations)
        for attempt_index in range(1, attempts + 1):
            _restore_session_snapshot(cwd, snapshot)
            prepared_attempt = prepare_operator_candidate_attempt(
                cwd=cwd,
                provider=provider,
                imported=imported,
                packet=packet,
                current_sha=current_sha,
                packet_prior_attempts=packet_prior_attempts,
                execution=execution,
                snapshot=snapshot,
                attempt_index=attempt_index,
                require_compile=require_compile,
                runtime_mode=runtime_mode,
                quality_mode=quality_mode,
            )
            candidate_result = prepared_attempt.candidate_result
            candidate_text = prepared_attempt.candidate_text
            require_issue_progress = prepared_attempt.require_issue_progress

            evaluated_attempt = evaluate_operator_candidate_attempt(
                cwd=cwd,
                provider=provider,
                imported=imported,
                before_text=before_text,
                current_sha=current_sha,
                base_quality_eval=base_quality_eval,
                base_tier2_failures=base_tier2_failures,
                base_active_failures=base_active_failures,
                packet_prior_attempts=packet_prior_attempts,
                execution=execution,
                intent=intent,
                attempt_index=attempt_index,
                candidate_result=candidate_result,
                candidate_text=candidate_text,
                require_issue_progress=require_issue_progress,
                require_compile=require_compile,
                quality_mode=quality_mode,
                max_iterations=max_iterations,
                require_live_verification=require_live_verification,
                accept_mixed_provenance=accept_mixed_provenance,
                runtime_mode=runtime_mode,
                citation_evidence_mode=citation_evidence_mode,
                citation_provider_name=citation_provider_name,
                citation_provider_command=citation_provider_command,
            )
            execution["attempts"].append(evaluated_attempt.attempt_record)
            final_incorporation = evaluated_attempt.incorporation
            final_verification = evaluated_attempt.verification
            final_candidate_result = evaluated_attempt.candidate_result
            if evaluated_attempt.gate_passed:
                execution["promotion_status"] = "promoted"
                execution["promotion_reason"] = "operator_candidate_passed_hard_gate"
                _promote_candidate_text(cwd, candidate_result["candidate_path"], snapshot.get("paper_path"))
                promoted_verification = _verification_snapshot(
                    cwd,
                    provider=provider,
                    require_compile=require_compile,
                    quality_mode=quality_mode,
                    max_iterations=max_iterations,
                    require_live_verification=require_live_verification,
                    accept_mixed_provenance=accept_mixed_provenance,
                    runtime_mode=runtime_mode,
                    citation_evidence_mode=citation_evidence_mode,
                    citation_provider_name=citation_provider_name,
                    citation_provider_command=citation_provider_command,
                    validation_name=f"validation.operator-feedback.promoted-{attempt_index:02d}.json",
                )
                final_verification = promoted_verification
                execution["post_promotion_qa_verdict"] = str(promoted_verification["plan"].get("verdict"))
                evaluated_attempt.attempt_record["promoted_canonical_verification"] = _verification_block(promoted_verification)
                break
        else:
            rollback = rollback_operator_feedback_candidate(
                cwd=cwd,
                provider=provider,
                snapshot=snapshot,
                execution=execution,
                intent=intent,
                require_compile=require_compile,
                quality_mode=quality_mode,
                max_iterations=max_iterations,
                require_live_verification=require_live_verification,
                accept_mixed_provenance=accept_mixed_provenance,
                runtime_mode=runtime_mode,
                citation_evidence_mode=citation_evidence_mode,
                citation_provider_name=citation_provider_name,
                citation_provider_command=citation_provider_command,
            )
            final_verification = rollback.verification

        if execution["promotion_status"] != "promoted" and final_verification is None:
            final_verification = _verification_snapshot(
                cwd,
                provider=provider,
                require_compile=False,
                quality_mode=quality_mode,
                max_iterations=max_iterations,
                require_live_verification=require_live_verification,
                accept_mixed_provenance=accept_mixed_provenance,
                runtime_mode=runtime_mode,
                citation_evidence_mode=citation_evidence_mode,
                citation_provider_name=citation_provider_name,
                citation_provider_command=citation_provider_command,
                validation_name="validation.operator-feedback.no-promotion.json",
            )
        finalized = finalize_operator_feedback_execution(
            cwd=cwd,
            imported=imported,
            current_sha=current_sha,
            execution=execution,
            final_verification=final_verification,
            final_candidate_result=final_candidate_result,
            final_incorporation=final_incorporation,
            owner_categories=owner_categories,
            intent=intent,
            max_supervised_iterations=max_supervised_iterations,
        )
        return finalized.execution_path, finalized.execution
    except Exception as exc:
        exception_result = handle_operator_feedback_exception(
            cwd=cwd,
            provider=provider,
            snapshot=snapshot,
            execution=execution,
            owner_categories=owner_categories,
            exc=exc,
            quality_mode=quality_mode,
            max_iterations=max_iterations,
            require_live_verification=require_live_verification,
            accept_mixed_provenance=accept_mixed_provenance,
            runtime_mode=runtime_mode,
            citation_evidence_mode=citation_evidence_mode,
            citation_provider_name=citation_provider_name,
            citation_provider_command=citation_provider_command,
        )
        return exception_result.execution_path, exception_result.execution
