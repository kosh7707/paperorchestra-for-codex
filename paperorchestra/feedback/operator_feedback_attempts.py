from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.runtime.providers import BaseProvider
from paperorchestra.feedback.operator_candidates import (
    _candidate_approval_source_role,
    _failed_operator_candidate_result,
    _generate_operator_candidate,
    _preserve_operator_candidate_for_attempt,
    _ready_candidate_from_packet,
    _stage_candidate_text_for_verification,
)
from paperorchestra.feedback.operator_snapshots import _restore_session_snapshot


@dataclass(frozen=True)
class PreparedOperatorCandidateAttempt:
    candidate_result: dict[str, Any]
    candidate_text: str
    require_issue_progress: bool


def prepare_operator_candidate_attempt(
    *,
    cwd: str | Path | None,
    provider: BaseProvider,
    imported: dict[str, Any],
    packet: dict[str, Any],
    current_sha: str,
    packet_prior_attempts: list[dict[str, Any]],
    execution: dict[str, Any],
    snapshot: dict[str, Any],
    attempt_index: int,
    require_compile: bool,
    runtime_mode: str,
    quality_mode: str,
) -> PreparedOperatorCandidateAttempt:
    intent = str(imported.get("intent") or "")
    if intent == "approve_existing_candidate":
        candidate_result = _ready_candidate_from_packet(
            packet,
            current_sha,
            source_artifact_role=_candidate_approval_source_role(imported),
        )
        candidate_text = _stage_candidate_text_for_verification(cwd, candidate_result["candidate_path"])
        return PreparedOperatorCandidateAttempt(
            candidate_result=candidate_result,
            candidate_text=candidate_text,
            require_issue_progress=False,
        )

    if intent == "generate_new_operator_candidate":
        prior_attempts_for_candidate = [*packet_prior_attempts, *(execution.get("attempts") or [])]
        try:
            candidate_result = _generate_operator_candidate(
                cwd,
                provider,
                imported,
                require_compile=require_compile,
                runtime_mode=runtime_mode,
                quality_mode=quality_mode,
                prior_attempts=prior_attempts_for_candidate,
            )
        except Exception as exc:
            _restore_session_snapshot(cwd, snapshot)
            candidate_result = _failed_operator_candidate_result(cwd, exc)
        candidate_text = candidate_result.get("candidate_text") or ""
        if candidate_result.get("candidate_path"):
            candidate_result = _preserve_operator_candidate_for_attempt(
                cwd,
                candidate_result,
                attempt_index=attempt_index,
            )
            candidate_text = _stage_candidate_text_for_verification(cwd, candidate_result["candidate_path"])
        return PreparedOperatorCandidateAttempt(
            candidate_result=candidate_result,
            candidate_text=candidate_text,
            require_issue_progress=True,
        )

    if intent == "reject_candidate_with_reason":  # pragma: no cover - attempts is zero for explicit rejection
        raise ContractError("operator rejection does not prepare a candidate attempt")
    raise ContractError(f"unsupported imported operator intent: {intent}")
