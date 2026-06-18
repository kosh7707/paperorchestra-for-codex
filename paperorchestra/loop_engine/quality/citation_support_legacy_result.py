from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.loop_engine.quality.citation_support_legacy_analysis import LegacyCitationSupportAnalysis
from paperorchestra.loop_engine.quality.utils import _file_sha256


def legacy_stale_result(path: Path, payload: dict[str, Any], *, current_sha: str) -> dict[str, Any]:
    return {
        "status": "fail",
        "path": str(path),
        "failing_codes": ["citation_support_review_stale"],
        "summary": None,
        "expected_manuscript_sha256": current_sha,
        "actual_manuscript_sha256": payload.get("manuscript_sha256"),
    }


def build_legacy_citation_support_result(
    path: Path,
    payload: dict[str, Any],
    analysis: LegacyCitationSupportAnalysis,
) -> dict[str, Any]:
    failing_codes = legacy_failing_codes(analysis)
    return {
        "status": "fail" if failing_codes else "pass",
        "path": str(path),
        "citation_review_sha256": _file_sha256(path),
        "summary": analysis.summary,
        "canonical_summary": analysis.summary,
        "reported_summary": analysis.reported_summary,
        "unsupported_count": analysis.unsupported,
        "contradicted_count": analysis.contradicted,
        "weakly_supported_count": analysis.weak,
        "needs_manual_check_count": analysis.manual,
        "metadata_only_count": analysis.metadata_only,
        "insufficient_evidence_count": analysis.insufficient,
        "evidence_missing_count": analysis.evidence_missing_count,
        "non_web_supported_count": analysis.non_web_supported_count,
        "untrusted_web_provenance_count": analysis.untrusted_web_provenance_count,
        "trace_missing_count": analysis.trace_missing_count,
        "trace_mismatch_count": analysis.trace_mismatch_count,
        "trace_invalid_count": analysis.trace_invalid_count,
        "review_trace_path": analysis.trace_path,
        "review_trace_sha256": analysis.trace_sha,
        "actual_review_trace_sha256": analysis.actual_trace_sha,
        "invalid_status_count": analysis.invalid_status_count,
        "invalid_status_values": analysis.invalid_status_values,
        "claims_checked": analysis.claims_checked,
        "item_count": len(analysis.items),
        "current_cited_sentence_count": analysis.current_cited_sentence_count,
        "citation_map_sha256": payload.get("citation_map_sha256"),
        "expected_citation_map_sha256": analysis.current_citation_map_sha,
        "expected_web_provider_command_digest": analysis.expected_web_digest,
        "evidence_mode": payload.get("review_mode") or analysis.provenance.get("mode"),
        "semantic_scholar_required": analysis.provenance.get("semantic_scholar_required"),
        "web_search_required": analysis.provenance.get("web_search_required"),
        "model_review_used": analysis.model_review_used,
        "legacy_untrusted": analysis.legacy_untrusted,
        "failing_codes": failing_codes,
    }


def legacy_failing_codes(analysis: LegacyCitationSupportAnalysis) -> list[str]:
    checks: tuple[tuple[bool | int, str], ...] = (
        (analysis.unsupported, "citation_support_unsupported"),
        (analysis.contradicted, "citation_support_contradicted"),
        (analysis.weak, "citation_support_weak"),
        (analysis.manual, "citation_support_manual_check"),
        (analysis.metadata_only, "citation_support_metadata_only"),
        (analysis.insufficient, "citation_support_insufficient_evidence"),
        (analysis.evidence_missing_count, "citation_support_evidence_missing"),
        (analysis.legacy_untrusted, "citation_support_review_legacy_untrusted"),
        (analysis.summary_mismatch, "citation_support_summary_mismatch"),
        (analysis.claim_count_mismatch, "citation_support_claim_count_mismatch"),
        (analysis.cited_sentence_coverage_mismatch, "citation_support_sentence_coverage_mismatch"),
        (analysis.citation_map_stale, "citation_support_citation_map_stale"),
        (analysis.invalid_status_count, "citation_support_invalid_status"),
        (analysis.non_web_supported_count, "citation_support_non_web_supported"),
        (analysis.untrusted_web_provenance_count, "citation_support_untrusted_web_provenance"),
        (analysis.trace_missing_count, "citation_support_trace_missing"),
        (analysis.trace_mismatch_count, "citation_support_trace_mismatch"),
        (analysis.trace_invalid_count, "citation_support_trace_invalid"),
    )
    return [code for active, code in checks if active]
