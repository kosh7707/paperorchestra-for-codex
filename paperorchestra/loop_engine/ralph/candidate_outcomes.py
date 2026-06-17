from __future__ import annotations

from typing import Any, Literal

from .state import _artifact_sha

CandidateOutcome = Literal["none", "auto_commit", "citation_support_rejected", "auto_commit_gate_rejected"]

_CANDIDATE_REJECTION_REASON = "semi_auto citation repair did not satisfy the auto-commit safety gate"


def classify_candidate_outcome(
    *,
    citation_candidate_applied: bool,
    auto_commit_allowed: bool,
    after_codes: set[str],
) -> CandidateOutcome:
    if not citation_candidate_applied:
        return "none"
    if auto_commit_allowed:
        return "auto_commit"
    if any(code.startswith("citation_support_") for code in after_codes):
        return "citation_support_rejected"
    return "auto_commit_gate_rejected"


def build_auto_commit_record(
    *,
    candidate_path: str | None,
    auto_commit_reason: str,
    residual_citation_failures: list[str],
    after_codes: set[str],
) -> dict[str, Any]:
    return {
        "status": "committed_for_continued_qa",
        "reason": auto_commit_reason,
        "candidate_path": candidate_path,
        "candidate_sha256": _artifact_sha(candidate_path),
        "residual_citation_failures": residual_citation_failures,
        "after_failing_codes": sorted(after_codes),
    }


def build_citation_support_rejection_records(
    *,
    candidate_path: str | None,
    residual_citation_failures: list[str],
    auto_commit_reason: str,
) -> dict[str, dict[str, Any]]:
    return {
        "rollback": {
            "reason": "citation_support_approval_failed",
            "failing_codes": residual_citation_failures,
            "auto_commit_blocked_reason": auto_commit_reason,
        },
        "handoff": {
            "status": "human_needed_candidate_rejected_by_citation_support",
            "reason": _CANDIDATE_REJECTION_REASON,
            "candidate_path": candidate_path,
            "residual_citation_failures": residual_citation_failures,
            "auto_commit_blocked_reason": auto_commit_reason,
        },
    }


def build_auto_commit_rejection_records(
    *,
    candidate_path: str | None,
    auto_commit_reason: str,
    after_codes: set[str],
) -> dict[str, dict[str, Any]]:
    return {
        "rollback": {
            "reason": "citation_candidate_auto_commit_blocked",
            "auto_commit_blocked_reason": auto_commit_reason,
            "failing_codes": sorted(after_codes),
        },
        "handoff": {
            "status": "human_needed_candidate_rejected_by_auto_commit_gate",
            "reason": _CANDIDATE_REJECTION_REASON,
            "candidate_path": candidate_path,
            "auto_commit_blocked_reason": auto_commit_reason,
        },
    }


def should_override_no_progress(
    *,
    verdict: str,
    actions_attempted: list[dict[str, Any]],
    final_progress: dict[str, Any],
    citation_candidate_applied: bool,
    candidate_progress: dict[str, Any],
) -> bool:
    return (
        verdict == "continue"
        and bool(actions_attempted)
        and not final_progress["forward_progress"]
        and not (citation_candidate_applied and candidate_progress.get("forward_progress"))
    )
