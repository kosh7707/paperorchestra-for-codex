from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paperorchestra.core.io import write_json
from paperorchestra.core.session import artifact_path
from paperorchestra.loop_engine.quality.loop import append_quality_loop_history
from paperorchestra.runtime.providers import BaseProvider
from paperorchestra.feedback.operator_completion import (
    _operator_exception_actionable_failures,
    _operator_exception_execution_update,
    _operator_exception_history_extra,
)
from paperorchestra.feedback.operator_snapshots import _restore_session_snapshot
from paperorchestra.feedback.operator_verification import _verification_block, _verification_snapshot


@dataclass(frozen=True)
class OperatorFeedbackExceptionResult:
    execution_path: Any
    execution: dict[str, Any]


def handle_operator_feedback_exception(
    *,
    cwd: str | Path | None,
    provider: BaseProvider,
    snapshot: dict[str, Any],
    execution: dict[str, Any],
    owner_categories: list[str],
    exc: Exception,
    quality_mode: str,
    max_iterations: int,
    require_live_verification: bool,
    accept_mixed_provenance: bool,
    runtime_mode: str,
    citation_evidence_mode: str,
    citation_provider_name: str | None,
    citation_provider_command: str | None,
) -> OperatorFeedbackExceptionResult:
    _restore_session_snapshot(cwd, snapshot)
    rollback_verification: dict[str, Any] | None = None
    try:
        rollback_verification = _verification_snapshot(
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
            validation_name="validation.operator-feedback.exception-rollback.json",
        )
    except Exception as verify_exc:  # pragma: no cover - defensive evidence best-effort
        rollback_verification = {"error": type(verify_exc).__name__ + ": " + str(verify_exc)}
    restored_block: dict[str, Any] = {}
    if rollback_verification and "validation_path" in rollback_verification:
        restored_block = _verification_block(rollback_verification)
    elif rollback_verification:
        restored_block = {"error": rollback_verification.get("error")}
    exception_actionable_failure, exception_history_actionable_failure = _operator_exception_actionable_failures(
        owner_categories=owner_categories,
        execution=execution,
        exc=exc,
    )
    execution.update(
        _operator_exception_execution_update(
            exc=exc,
            restored_block=restored_block,
            actionable_failure=exception_actionable_failure,
        )
    )
    execution_path = artifact_path(cwd, "operator_feedback.execution.json")
    write_json(execution_path, execution)
    if rollback_verification and "quality_eval" in rollback_verification:
        append_quality_loop_history(
            cwd,
            rollback_verification["quality_eval"],
            verdict="execution_error",
            plan_path=rollback_verification["plan_path"],
            quality_eval_path=rollback_verification["quality_path"],
            execution_path=execution_path,
            event_type="operator_feedback_cycle",
            consumes_budget=False,
            extra=_operator_exception_history_extra(execution, exception_history_actionable_failure, exc),
        )
    return OperatorFeedbackExceptionResult(execution_path=execution_path, execution=execution)
