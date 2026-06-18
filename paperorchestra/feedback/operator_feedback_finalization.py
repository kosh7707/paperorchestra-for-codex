from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paperorchestra.core.io import write_json
from paperorchestra.core.session import artifact_path, load_session
from paperorchestra.loop_engine.quality.loop import append_quality_loop_history
from paperorchestra.feedback.operator_completion import (
    _non_promoted_actionable_failure,
    _operator_executor_crashed,
    _operator_final_execution_update,
    _operator_history_extra,
)
from paperorchestra.feedback.operator_human_review_approval import _attach_candidate_approval_from_attempt
from paperorchestra.feedback.operator_human_review_readiness import _best_human_review_candidate_attempt
from paperorchestra.feedback.operator_records import _build_operator_incorporation_report
from paperorchestra.feedback.operator_verification import _verification_block
from paperorchestra.feedback.packet_artifacts import _file_sha256


@dataclass(frozen=True)
class FinalizedOperatorFeedback:
    execution_path: Any
    execution: dict[str, Any]


def finalize_operator_feedback_execution(
    *,
    cwd: str | Path | None,
    imported: dict[str, Any],
    current_sha: str,
    execution: dict[str, Any],
    final_verification: dict[str, Any] | None,
    final_candidate_result: dict[str, Any] | None,
    final_incorporation: list[dict[str, Any]],
    owner_categories: list[str],
    intent: str,
    max_supervised_iterations: int,
) -> FinalizedOperatorFeedback:
    execution_path = artifact_path(cwd, "operator_feedback.execution.json")
    promoted = execution["promotion_status"] == "promoted"
    executor_crashed = _operator_executor_crashed(execution)
    final_state = load_session(cwd)
    after_sha = _file_sha256(final_state.artifacts.paper_full_tex)
    non_promoted_actionable_failure = _non_promoted_actionable_failure(
        promoted=promoted,
        executor_crashed=executor_crashed,
        intent=intent,
        execution=execution,
        owner_categories=owner_categories,
    )
    incorporation_report = _build_operator_incorporation_report(
        imported=imported,
        current_sha=current_sha,
        after_sha=after_sha,
        promotion_status=execution["promotion_status"],
        actionable_failure=non_promoted_actionable_failure,
        issues=final_incorporation,
    )
    incorporation_path = artifact_path(cwd, "operator_feedback.incorporation.json")
    write_json(incorporation_path, incorporation_report)
    plan = final_verification["plan"] if final_verification else {}
    final_update = _operator_final_execution_update(
        execution=execution,
        promoted=promoted,
        executor_crashed=executor_crashed,
        plan=plan,
        max_supervised_iterations=max_supervised_iterations,
        after_sha=after_sha,
        final_candidate_result=final_candidate_result,
        incorporation_path=str(incorporation_path),
        verification_block=_verification_block(final_verification) if final_verification else {},
        actionable_failure=non_promoted_actionable_failure,
    )
    execution.update(final_update)
    verdict = str(final_update["verdict"])
    if not promoted:
        best_attempt = _best_human_review_candidate_attempt(execution.get("attempts") or [])
        if best_attempt is not None:
            _attach_candidate_approval_from_attempt(
                execution,
                best_attempt,
                execution_path=execution_path,
            )
    if executor_crashed:
        execution["error"] = "operator executor crashed during supervised feedback application"
    write_json(execution_path, execution)
    if final_verification:
        append_quality_loop_history(
            cwd,
            final_verification["quality_eval"],
            verdict=verdict,
            plan_path=final_verification["plan_path"],
            quality_eval_path=final_verification["quality_path"],
            execution_path=execution_path,
            event_type="operator_feedback_cycle",
            consumes_budget=False,
            extra=_operator_history_extra(execution, non_promoted_actionable_failure),
        )
    return FinalizedOperatorFeedback(execution_path=execution_path, execution=execution)
