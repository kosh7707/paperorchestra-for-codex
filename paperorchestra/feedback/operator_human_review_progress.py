from __future__ import annotations

from typing import Any

from paperorchestra.feedback import packet_artifacts as _packet_artifacts


def _citation_issue_count_from_summary(summary: dict[str, Any] | None) -> int | None:
    if not isinstance(summary, dict):
        return None
    total = 0
    found = False
    for key in _CITATION_ISSUE_COUNT_FIELDS:
        value = summary.get(key)
        if isinstance(value, int):
            found = True
            total += value
    return total if found else None


def _candidate_progress_from_attempt(
    execution: dict[str, Any],
    attempt: dict[str, Any],
    *,
    citation_summary: dict[str, Any] | None,
    active_metric_delta: dict[str, Any],
) -> dict[str, Any]:
    before_codes = [str(code) for code in attempt.get("base_active_failures") or []]
    after_codes = [str(code) for code in attempt.get("candidate_active_failures") or []]
    before_hash = _packet_artifacts._sha256_prefixed(execution.get("manuscript_sha256_before"))
    after_hash = _packet_artifacts._sha256_prefixed(_packet_artifacts._file_sha256(attempt.get("candidate_path")))
    before_issue_count, after_issue_count = _issue_count_pair(active_metric_delta, citation_summary)
    return {
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
        "citation_issue_delta": _issue_count_delta(before_issue_count, after_issue_count),
        "active_tier2_metric_delta": active_metric_delta,
        "forward_progress": True,
    }


def _issue_count_pair(
    active_metric_delta: dict[str, Any],
    citation_summary: dict[str, Any] | None,
) -> tuple[int | None, int | None]:
    before_issue_count = active_metric_delta.get("base_total")
    after_issue_count = active_metric_delta.get("candidate_total")
    if isinstance(before_issue_count, int) and isinstance(after_issue_count, int):
        return before_issue_count, after_issue_count
    return None, _citation_issue_count_from_summary(citation_summary)


def _issue_count_delta(before_issue_count: int | None, after_issue_count: int | None) -> int | None:
    if isinstance(before_issue_count, int) and isinstance(after_issue_count, int):
        return after_issue_count - before_issue_count
    return None


_CITATION_ISSUE_COUNT_FIELDS = (
    "weakly_supported",
    "unsupported",
    "insufficient_evidence",
    "needs_manual_check",
    "manual_check",
    "contradicted",
    "metadata_only",
    "evidence_missing",
)
