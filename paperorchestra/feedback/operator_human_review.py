from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.models import utc_now_iso
from paperorchestra.feedback import packet_artifacts as _packet_artifacts
from paperorchestra.feedback import packet_bindings as _packet_bindings
from paperorchestra.feedback.operator_contract import HUMAN_REVIEWABLE_NEW_TIER2_CODES


def _candidate_attempt_ready_for_human_review(attempt: dict[str, Any]) -> bool:
    if not attempt.get("resolved_active_failures"):
        return False
    if not attempt.get("candidate_path"):
        return False
    if not Path(str(attempt.get("candidate_path"))).exists():
        return False
    disqualifying_reasons = {
        "no_textual_change",
        "executor_crashed",
        "executor_returned_identical_content",
        "validation_failed",
        "compile_failed",
        "tier0_failed",
        "tier1_failed",
        "active_blocker_metric_progress_missing",
        "active_blocker_progress_missing",
        "active_tier2_metric_regression",
        "protected_supported_citation_regression",
        "issue_progress_missing",
        "repeated_non_promotable_candidate",
        "reviewer_catastrophic_regression",
    }
    reasons = {str(reason) for reason in attempt.get("gate_reasons") or []}
    if reasons & disqualifying_reasons:
        return False
    new_tier2 = {str(code) for code in attempt.get("new_tier2_failures") or []}
    return new_tier2 <= HUMAN_REVIEWABLE_NEW_TIER2_CODES


def _best_human_review_candidate_attempt(attempts: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [attempt for attempt in attempts if _candidate_attempt_ready_for_human_review(attempt)]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda attempt: (
            len(attempt.get("resolved_active_failures") or []),
            -len(attempt.get("candidate_active_failures") or []),
            -int(attempt.get("attempt_index") or 0),
        ),
    )


def _citation_issue_count_from_summary(summary: dict[str, Any] | None) -> int | None:
    if not isinstance(summary, dict):
        return None
    total = 0
    found = False
    for key in (
        "weakly_supported",
        "unsupported",
        "insufficient_evidence",
        "needs_manual_check",
        "manual_check",
        "contradicted",
        "metadata_only",
        "evidence_missing",
    ):
        value = summary.get(key)
        if isinstance(value, int):
            found = True
            total += value
    return total if found else None


def _attach_candidate_approval_from_attempt(
    execution: dict[str, Any],
    attempt: dict[str, Any],
    *,
    execution_path: Path,
) -> None:
    before_codes = [str(code) for code in attempt.get("base_active_failures") or []]
    after_codes = [str(code) for code in attempt.get("candidate_active_failures") or []]
    before_hash = _packet_artifacts._sha256_prefixed(execution.get("manuscript_sha256_before"))
    after_hash = _packet_artifacts._sha256_prefixed(
        _packet_artifacts._file_sha256(attempt.get("candidate_path"))
    )
    verification = attempt.get("verification") if isinstance(attempt.get("verification"), dict) else {}
    citation_summary = None
    citation_block = verification.get("citation_support_review") if isinstance(verification, dict) else None
    if isinstance(citation_block, dict):
        citation_summary = citation_block.get("summary")
    active_metric_delta = attempt.get("active_tier2_metric_delta") if isinstance(attempt.get("active_tier2_metric_delta"), dict) else {}
    before_issue_count = active_metric_delta.get("base_total")
    after_issue_count = active_metric_delta.get("candidate_total")
    if not isinstance(before_issue_count, int) or not isinstance(after_issue_count, int):
        before_issue_count = None
        after_issue_count = _citation_issue_count_from_summary(citation_summary)
    progress = {
        "resolved_codes": [str(code) for code in attempt.get("resolved_active_failures") or []],
        "new_codes": [str(code) for code in attempt.get("candidate_active_failures") or [] if code not in before_codes],
        "before_failing_codes": before_codes,
        "after_failing_codes": after_codes,
        "before_manuscript_hash": before_hash,
        "after_manuscript_hash": after_hash,
        "same_manuscript_as_previous": before_hash == after_hash if before_hash and after_hash else None,
        "manuscript_identity_known": bool(before_hash and after_hash),
        "before_citation_issue_count": before_issue_count,
        "after_citation_issue_count": after_issue_count,
        "citation_issue_delta": (after_issue_count - before_issue_count) if isinstance(before_issue_count, int) and isinstance(after_issue_count, int) else None,
        "active_tier2_metric_delta": active_metric_delta,
        "forward_progress": True,
    }
    approval = {
        "status": "human_needed_candidate_ready",
        "candidate_path": attempt.get("candidate_path"),
        "candidate_sha256": _packet_artifacts._sha256_prefixed(
            _packet_artifacts._sha256_digest(str(attempt.get("candidate_sha256") or ""))
            or _packet_artifacts._file_sha256(attempt.get("candidate_path"))
        ),
        "base_manuscript_sha256": before_hash,
        "source_execution_path": str(execution_path),
        "source_execution_sha256": "",
        "created_at": utc_now_iso(),
        "reason": "supervised operator candidate made net progress but introduced only human-reviewable claim-safety uncertainty",
    }
    execution["candidate_approval"] = approval
    execution["candidate_progress"] = progress
    execution["candidate_state"] = {
        "manuscript_path": attempt.get("candidate_path"),
        "verification": verification,
        "after": {
            "failing_codes": after_codes,
            "citation_support_summary": citation_summary,
        },
        "quality_eval_path": (verification.get("quality_eval") or {}).get("path") if isinstance(verification.get("quality_eval"), dict) else None,
        "qa_loop_plan_path": (verification.get("qa_loop_plan") or {}).get("path") if isinstance(verification.get("qa_loop_plan"), dict) else None,
        "qa_loop_plan_verdict": (verification.get("qa_loop_plan") or {}).get("verdict") if isinstance(verification.get("qa_loop_plan"), dict) else None,
        "progress": progress,
    }
    approval["source_execution_sha256"] = _packet_bindings._execution_payload_sha256(execution)
