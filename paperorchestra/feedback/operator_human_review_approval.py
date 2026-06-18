from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.models import utc_now_iso
from paperorchestra.feedback import packet_artifacts as _packet_artifacts
from paperorchestra.feedback import packet_bindings as _packet_bindings
from paperorchestra.feedback.operator_human_review_progress import _candidate_progress_from_attempt


def _attach_candidate_approval_from_attempt(
    execution: dict[str, Any],
    attempt: dict[str, Any],
    *,
    execution_path: Path,
) -> None:
    verification = attempt.get("verification") if isinstance(attempt.get("verification"), dict) else {}
    citation_summary = _citation_summary(verification)
    active_metric_delta = attempt.get("active_tier2_metric_delta") if isinstance(attempt.get("active_tier2_metric_delta"), dict) else {}
    progress = _candidate_progress_from_attempt(
        execution,
        attempt,
        citation_summary=citation_summary,
        active_metric_delta=active_metric_delta,
    )
    approval = _candidate_approval_payload(execution, attempt, execution_path=execution_path)
    execution["candidate_approval"] = approval
    execution["candidate_progress"] = progress
    execution["candidate_state"] = _candidate_state(attempt, verification=verification, citation_summary=citation_summary, progress=progress)
    approval["source_execution_sha256"] = _packet_bindings._execution_payload_sha256(execution)


def _citation_summary(verification: dict[str, Any]) -> dict[str, Any] | None:
    citation_block = verification.get("citation_support_review") if isinstance(verification, dict) else None
    if not isinstance(citation_block, dict):
        return None
    summary = citation_block.get("summary")
    return summary if isinstance(summary, dict) else None


def _candidate_approval_payload(
    execution: dict[str, Any],
    attempt: dict[str, Any],
    *,
    execution_path: Path,
) -> dict[str, Any]:
    return {
        "status": "human_needed_candidate_ready",
        "candidate_path": attempt.get("candidate_path"),
        "candidate_sha256": _candidate_sha256(attempt),
        "base_manuscript_sha256": _packet_artifacts._sha256_prefixed(execution.get("manuscript_sha256_before")),
        "source_execution_path": str(execution_path),
        "source_execution_sha256": "",
        "created_at": utc_now_iso(),
        "reason": "supervised operator candidate made net progress but introduced only human-reviewable claim-safety uncertainty",
    }


def _candidate_sha256(attempt: dict[str, Any]) -> str | None:
    digest = _packet_artifacts._sha256_digest(str(attempt.get("candidate_sha256") or ""))
    return _packet_artifacts._sha256_prefixed(digest or _packet_artifacts._file_sha256(attempt.get("candidate_path")))


def _candidate_state(
    attempt: dict[str, Any],
    *,
    verification: dict[str, Any],
    citation_summary: dict[str, Any] | None,
    progress: dict[str, Any],
) -> dict[str, Any]:
    quality_eval = verification.get("quality_eval") if isinstance(verification.get("quality_eval"), dict) else {}
    qa_loop_plan = verification.get("qa_loop_plan") if isinstance(verification.get("qa_loop_plan"), dict) else {}
    return {
        "manuscript_path": attempt.get("candidate_path"),
        "verification": verification,
        "after": {
            "failing_codes": [str(code) for code in attempt.get("candidate_active_failures") or []],
            "citation_support_summary": citation_summary,
        },
        "quality_eval_path": quality_eval.get("path"),
        "qa_loop_plan_path": qa_loop_plan.get("path"),
        "qa_loop_plan_verdict": qa_loop_plan.get("verdict"),
        "progress": progress,
    }
