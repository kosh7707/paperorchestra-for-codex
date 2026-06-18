from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.feedback.operator_feedback_context import load_operator_feedback_context
from paperorchestra.feedback.operator_feedback_exception import handle_operator_feedback_exception
from paperorchestra.feedback.operator_feedback_finalization import finalize_operator_feedback_execution
from paperorchestra.feedback.operator_feedback_loop import (
    ensure_operator_feedback_final_verification,
    run_operator_feedback_attempts,
)
from paperorchestra.feedback.operator_feedback_options import OperatorFeedbackOptions
from paperorchestra.feedback.operator_snapshots import _session_snapshot
from paperorchestra.runtime.provider_base import BaseProvider


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
    options = OperatorFeedbackOptions(
        max_supervised_iterations=max_supervised_iterations,
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
    context = load_operator_feedback_context(
        cwd=cwd,
        imported_feedback_path=imported_feedback_path,
        max_supervised_iterations=max_supervised_iterations,
    )
    snapshot = _session_snapshot(cwd)
    before_text = snapshot.get("paper_text") or ""
    execution = context.execution

    try:
        loop_result = run_operator_feedback_attempts(
            cwd=cwd,
            provider=provider,
            context=context,
            snapshot=snapshot,
            before_text=before_text,
            options=options,
        )
        final_verification = ensure_operator_feedback_final_verification(
            cwd=cwd,
            provider=provider,
            execution=execution,
            final_verification=loop_result.final_verification,
            options=options,
        )
        finalized = finalize_operator_feedback_execution(
            cwd=cwd,
            imported=context.imported,
            current_sha=context.current_sha,
            execution=execution,
            final_verification=final_verification,
            final_candidate_result=loop_result.final_candidate_result,
            final_incorporation=loop_result.final_incorporation,
            owner_categories=context.owner_categories,
            intent=context.intent,
            max_supervised_iterations=max_supervised_iterations,
        )
        return finalized.execution_path, finalized.execution
    except Exception as exc:
        exception_result = handle_operator_feedback_exception(
            cwd=cwd,
            provider=provider,
            snapshot=snapshot,
            execution=execution,
            owner_categories=context.owner_categories,
            exc=exc,
            **options.exception_kwargs(),
        )
        return exception_result.execution_path, exception_result.execution
