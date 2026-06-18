from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.core.session import load_session
from paperorchestra.feedback.operator_candidates import (
    _load_packet_from_imported,
    _packet_artifact_payload,
    _packet_prior_operator_attempts,
)
from paperorchestra.feedback.operator_contract import _load_imported_feedback
from paperorchestra.feedback.operator_gates import _quality_failing_codes, _tier_failing_codes
from paperorchestra.feedback.operator_records import _build_operator_execution_record
from paperorchestra.feedback.packet_artifacts import _file_sha256


@dataclass(frozen=True)
class OperatorFeedbackContext:
    imported_path: Path
    imported: dict[str, Any]
    packet: dict[str, Any]
    intent: str
    state: Any
    current_sha: str
    base_quality_eval: dict[str, Any] | None
    packet_prior_attempts: list[dict[str, Any]]
    base_tier2_failures: set[str]
    base_active_failures: set[str]
    execution: dict[str, Any]
    owner_categories: list[str]


def load_operator_feedback_context(
    *,
    cwd: str | Path | None,
    imported_feedback_path: str | Path,
    max_supervised_iterations: int,
) -> OperatorFeedbackContext:
    imported_path = Path(imported_feedback_path).resolve()
    imported = _load_imported_feedback(imported_path)
    packet = _load_packet_from_imported(imported)
    intent = str(imported.get("intent") or "")
    state = load_session(cwd)
    current_sha = _file_sha256(state.artifacts.paper_full_tex)
    if current_sha != imported.get("manuscript_sha256"):
        raise ContractError("imported operator feedback is stale for the current manuscript")

    base_quality_eval = _packet_artifact_payload(packet, "quality_eval")
    packet_prior_attempts = _packet_prior_operator_attempts(packet)
    base_tier2_failures = set(_tier_failing_codes(base_quality_eval, "tier_2_claim_safety"))
    base_active_failures = set(_quality_failing_codes(base_quality_eval or {}))
    owner_categories = [str(issue.get("owner_category") or "author") for issue in imported.get("issues") or []]
    execution = _build_operator_execution_record(
        imported_path,
        imported,
        current_sha=current_sha,
        max_supervised_iterations=max_supervised_iterations,
        intent=intent,
    )

    return OperatorFeedbackContext(
        imported_path=imported_path,
        imported=imported,
        packet=packet,
        intent=intent,
        state=state,
        current_sha=current_sha,
        base_quality_eval=base_quality_eval,
        packet_prior_attempts=packet_prior_attempts,
        base_tier2_failures=base_tier2_failures,
        base_active_failures=base_active_failures,
        execution=execution,
        owner_categories=owner_categories,
    )


def operator_feedback_attempt_count(*, intent: str, max_supervised_iterations: int) -> int:
    if intent == "reject_candidate_with_reason":
        return 0
    if intent == "approve_existing_candidate":
        return 1
    return max_supervised_iterations
