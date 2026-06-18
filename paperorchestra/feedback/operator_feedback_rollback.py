from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paperorchestra.runtime.provider_base import BaseProvider
from paperorchestra.feedback.operator_snapshots import _restore_session_snapshot
from paperorchestra.feedback.operator_verification import _verification_block, _verification_snapshot


@dataclass(frozen=True)
class OperatorFeedbackRollback:
    verification: dict[str, Any]


def rollback_operator_feedback_candidate(
    *,
    cwd: str | Path | None,
    provider: BaseProvider,
    snapshot: dict[str, Any],
    execution: dict[str, Any],
    intent: str,
    require_compile: bool,
    quality_mode: str,
    max_iterations: int,
    require_live_verification: bool,
    accept_mixed_provenance: bool,
    runtime_mode: str,
    citation_evidence_mode: str,
    citation_provider_name: str | None,
    citation_provider_command: str | None,
) -> OperatorFeedbackRollback:
    _restore_session_snapshot(cwd, snapshot)
    rollback_verification = _verification_snapshot(
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
        validation_name="validation.operator-feedback.rollback.json",
    )
    explicit_rejection = intent == "reject_candidate_with_reason"
    execution["promotion_status"] = "rolled_back"
    execution["promotion_reason"] = "operator_rejected_candidate" if explicit_rejection else "operator_candidate_failed_hard_gate"
    execution["candidate_rollback"] = {
        "reason": "operator_rejected_candidate" if explicit_rejection else "supervised_candidate_failed_hard_gate",
        "restored_verification": _verification_block(rollback_verification),
    }
    return OperatorFeedbackRollback(verification=rollback_verification)
