from __future__ import annotations

from pathlib import Path
from typing import Any

from .utils import _file_sha256
from .citation_support_v3_summary import CitationSupportV3Summary


def v3_failing_codes(
    *,
    reported_summary: dict[str, Any],
    summary: CitationSupportV3Summary,
    identity_mismatch: bool,
    context_mismatch_count: int,
    missing_source_artifacts: int,
) -> list[str]:
    failing_codes: list[str] = []
    if reported_summary != summary.counts:
        failing_codes.append("citation_support_summary_mismatch")
    if summary.invalid_verdicts:
        failing_codes.append("citation_support_invalid_status")
    if identity_mismatch:
        failing_codes.append("citation_support_case_coverage_mismatch")
    if context_mismatch_count:
        failing_codes.append("citation_support_case_context_mismatch")
    if summary.counts["weak"]:
        failing_codes.append("citation_support_weak")
    if summary.counts["fail"]:
        failing_codes.append("citation_support_unsupported")
    if summary.counts["human_needed"]:
        failing_codes.append("citation_support_manual_check")
    if missing_source_artifacts:
        failing_codes.append("citation_support_evidence_missing")
    return failing_codes


def build_v3_citation_support_result(
    *,
    path: Path,
    payload: dict[str, Any],
    cases: list[dict[str, Any]],
    current_cases: list[dict[str, Any]],
    review_context_count: int,
    current_context_count: int,
    context_mismatch_indexes: list[int],
    missing_source_artifacts: int,
    summary: CitationSupportV3Summary,
    reported_summary: dict[str, Any],
    failing_codes: list[str],
) -> dict[str, Any]:
    status = "fail" if failing_codes else "pass"
    return {
        "status": status,
        "path": str(path),
        "citation_review_sha256": _file_sha256(path),
        "summary": summary.counts,
        "canonical_summary": summary.counts,
        "reported_summary": reported_summary,
        "claims_checked": len(cases),
        "item_count": len(cases),
        "case_count": len(cases),
        "current_case_count": len(current_cases),
        "weakly_supported_count": summary.counts["weak"],
        "unsupported_count": summary.counts["fail"],
        "needs_manual_check_count": summary.counts["human_needed"],
        "evidence_missing_count": missing_source_artifacts,
        "context_mismatch_count": len(context_mismatch_indexes),
        "context_mismatch_indexes": context_mismatch_indexes,
        "review_case_context_count": review_context_count,
        "current_case_context_count": current_context_count,
        "evidence_mode": payload.get("mode"),
        "source_backed": True,
        "legacy_untrusted": False,
        "invalid_status_values": sorted(set(summary.invalid_verdicts)),
        "failing_codes": failing_codes,
    }
