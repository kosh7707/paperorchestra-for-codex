from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from paperorchestra.feedback.operator_feedback_attempts import prepare_operator_candidate_attempt
from paperorchestra.feedback.operator_feedback_context import OperatorFeedbackContext, operator_feedback_attempt_count
from paperorchestra.feedback.operator_feedback_evaluation import evaluate_operator_candidate_attempt
from paperorchestra.feedback.operator_feedback_options import OperatorFeedbackOptions
from paperorchestra.feedback.operator_feedback_promotion import promote_operator_feedback_attempt
from paperorchestra.feedback.operator_feedback_rollback import rollback_operator_feedback_candidate
from paperorchestra.feedback.operator_snapshots import _restore_session_snapshot
from paperorchestra.feedback.operator_verification import _verification_snapshot
from paperorchestra.runtime.providers import BaseProvider


@dataclass(frozen=True)
class OperatorFeedbackLoopResult:
    final_incorporation: list[dict[str, Any]] = field(default_factory=list)
    final_verification: dict[str, Any] | None = None
    final_candidate_result: dict[str, Any] | None = None


def run_operator_feedback_attempts(
    *,
    cwd: str | Path | None,
    provider: BaseProvider,
    context: OperatorFeedbackContext,
    snapshot: dict[str, Any],
    before_text: str,
    options: OperatorFeedbackOptions,
) -> OperatorFeedbackLoopResult:
    attempts = operator_feedback_attempt_count(
        intent=context.intent,
        max_supervised_iterations=options.max_supervised_iterations,
    )
    final_incorporation: list[dict[str, Any]] = []
    final_verification: dict[str, Any] | None = None
    final_candidate_result: dict[str, Any] | None = None

    for attempt_index in range(1, attempts + 1):
        _restore_session_snapshot(cwd, snapshot)
        evaluated_attempt = _prepare_and_evaluate_attempt(
            cwd=cwd,
            provider=provider,
            context=context,
            snapshot=snapshot,
            before_text=before_text,
            attempt_index=attempt_index,
            options=options,
        )
        context.execution["attempts"].append(evaluated_attempt.attempt_record)
        final_incorporation = evaluated_attempt.incorporation
        final_verification = evaluated_attempt.verification
        final_candidate_result = evaluated_attempt.candidate_result
        if evaluated_attempt.gate_passed:
            promotion = promote_operator_feedback_attempt(
                cwd=cwd,
                provider=provider,
                snapshot=snapshot,
                execution=context.execution,
                candidate_result=evaluated_attempt.candidate_result,
                attempt_record=evaluated_attempt.attempt_record,
                attempt_index=attempt_index,
                options=options,
            )
            return OperatorFeedbackLoopResult(
                final_incorporation=final_incorporation,
                final_verification=promotion.verification,
                final_candidate_result=final_candidate_result,
            )

    rollback = rollback_operator_feedback_candidate(
        cwd=cwd,
        provider=provider,
        snapshot=snapshot,
        execution=context.execution,
        intent=context.intent,
        **options.rollback_kwargs(),
    )
    return OperatorFeedbackLoopResult(
        final_incorporation=final_incorporation,
        final_verification=rollback.verification,
        final_candidate_result=final_candidate_result,
    )


def _prepare_and_evaluate_attempt(
    *,
    cwd: str | Path | None,
    provider: BaseProvider,
    context: OperatorFeedbackContext,
    snapshot: dict[str, Any],
    before_text: str,
    attempt_index: int,
    options: OperatorFeedbackOptions,
):
    prepared_attempt = prepare_operator_candidate_attempt(
        cwd=cwd,
        provider=provider,
        imported=context.imported,
        packet=context.packet,
        current_sha=context.current_sha,
        packet_prior_attempts=context.packet_prior_attempts,
        execution=context.execution,
        snapshot=snapshot,
        attempt_index=attempt_index,
        **options.prepare_kwargs(),
    )
    return evaluate_operator_candidate_attempt(
        cwd=cwd,
        provider=provider,
        imported=context.imported,
        before_text=before_text,
        current_sha=context.current_sha,
        base_quality_eval=context.base_quality_eval,
        base_tier2_failures=context.base_tier2_failures,
        base_active_failures=context.base_active_failures,
        packet_prior_attempts=context.packet_prior_attempts,
        execution=context.execution,
        intent=context.intent,
        attempt_index=attempt_index,
        candidate_result=prepared_attempt.candidate_result,
        candidate_text=prepared_attempt.candidate_text,
        require_issue_progress=prepared_attempt.require_issue_progress,
        **options.evaluation_kwargs(),
    )


def ensure_operator_feedback_final_verification(
    *,
    cwd: str | Path | None,
    provider: BaseProvider,
    execution: dict[str, Any],
    final_verification: dict[str, Any] | None,
    options: OperatorFeedbackOptions,
) -> dict[str, Any] | None:
    if execution["promotion_status"] == "promoted" or final_verification is not None:
        return final_verification
    return _verification_snapshot(
        cwd,
        provider=provider,
        **options.verification_kwargs(
            "validation.operator-feedback.no-promotion.json",
            require_compile=False,
        ),
    )
