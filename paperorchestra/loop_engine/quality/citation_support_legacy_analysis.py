from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paperorchestra.loop_engine.quality.citation_support_legacy_evidence import (
    _evidence_counts,
    _expected_web_provider_digest,
    _trace_context,
)
from paperorchestra.loop_engine.quality.policy import CITATION_SUPPORT_STATUSES
from paperorchestra.loop_engine.quality.utils import _file_sha256, _read_json_if_exists
from paperorchestra.reviews.citation_sentences import extract_cited_sentences


@dataclass(frozen=True)
class LegacyCitationSupportAnalysis:
    items: list[dict[str, Any]]
    summary: dict[str, int]
    reported_summary: dict[str, Any]
    provenance: dict[str, Any]
    unsupported: int
    contradicted: int
    weak: int
    manual: int
    metadata_only: int
    insufficient: int
    invalid_status_count: int
    invalid_status_values: list[str]
    evidence_missing_count: int
    non_web_supported_count: int
    untrusted_web_provenance_count: int
    trace_missing_count: int
    trace_mismatch_count: int
    trace_invalid_count: int
    trace_path: Any
    trace_sha: Any
    actual_trace_sha: str | None
    claims_checked: Any
    current_cited_sentence_count: int
    current_citation_map_sha: str | None
    citation_map_stale: bool
    expected_web_digest: str | None
    model_review_used: bool
    legacy_untrusted: bool
    summary_mismatch: bool
    claim_count_mismatch: bool
    cited_sentence_coverage_mismatch: bool


def analyze_legacy_citation_support(
    state: Any,
    payload: dict[str, Any],
    *,
    quality_mode: str,
) -> LegacyCitationSupportAnalysis:
    items, summary, invalid_status_values = _items_and_summary(payload)
    provenance = payload.get("evidence_provenance") if isinstance(payload.get("evidence_provenance"), dict) else {}
    current_citation_map = _current_citation_map(state)
    trace = _trace_context(provenance)
    expected_web_digest = _expected_web_provider_digest(quality_mode)
    evidence_counts = _evidence_counts(
        items,
        payload=payload,
        provenance=provenance,
        current_citation_map=current_citation_map,
        trace=trace,
        expected_web_digest=expected_web_digest,
        quality_mode=quality_mode,
    )
    reported_summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    claims_checked = payload.get("claims_checked")
    current_cited_sentence_count = _current_cited_sentence_count(state)
    current_citation_map_sha = _file_sha256(state.artifacts.citation_map_json)
    return LegacyCitationSupportAnalysis(
        items=items,
        summary=summary,
        reported_summary=reported_summary,
        provenance=provenance,
        unsupported=int(summary.get("unsupported") or 0),
        contradicted=int(summary.get("contradicted") or 0),
        weak=int(summary.get("weakly_supported") or 0),
        manual=int(summary.get("needs_manual_check") or 0),
        metadata_only=int(summary.get("metadata_only") or 0),
        insufficient=int(summary.get("insufficient_evidence") or 0),
        invalid_status_count=len(invalid_status_values),
        invalid_status_values=sorted(set(invalid_status_values)),
        evidence_missing_count=evidence_counts["evidence_missing"],
        non_web_supported_count=evidence_counts["non_web_supported"],
        untrusted_web_provenance_count=evidence_counts["untrusted_web_provenance"],
        trace_missing_count=evidence_counts["trace_missing"],
        trace_mismatch_count=evidence_counts["trace_mismatch"],
        trace_invalid_count=evidence_counts["trace_invalid"],
        trace_path=trace["path"],
        trace_sha=trace["sha"],
        actual_trace_sha=trace["actual_sha"],
        claims_checked=claims_checked,
        current_cited_sentence_count=current_cited_sentence_count,
        current_citation_map_sha=current_citation_map_sha,
        citation_map_stale=bool(
            current_citation_map_sha and payload.get("citation_map_sha256") != current_citation_map_sha
        ),
        expected_web_digest=expected_web_digest,
        model_review_used=bool(provenance.get("model_review_used")),
        legacy_untrusted=_legacy_untrusted(payload, provenance),
        summary_mismatch=reported_summary != summary,
        claim_count_mismatch=claims_checked != len(items),
        cited_sentence_coverage_mismatch=current_cited_sentence_count != len(items),
    )


def _items_and_summary(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, int], list[str]]:
    raw_items = payload.get("items") if isinstance(payload.get("items"), list) else []
    items = [item for item in raw_items if isinstance(item, dict)]
    summary: dict[str, int] = {}
    invalid_values: list[str] = []
    for item in items:
        status_value = str(item.get("support_status") or "needs_manual_check")
        if status_value not in CITATION_SUPPORT_STATUSES:
            invalid_values.append(status_value)
        summary[status_value] = summary.get(status_value, 0) + 1
    return items, summary, invalid_values


def _legacy_untrusted(payload: dict[str, Any], provenance: dict[str, Any]) -> bool:
    return (
        payload.get("schema_version") != "citation-support-review/2"
        or provenance.get("claim_support_not_metadata_lookup") is not True
    )


def _current_cited_sentence_count(state: Any) -> int:
    if not state.artifacts.paper_full_tex or not Path(state.artifacts.paper_full_tex).exists():
        return 0
    text = Path(state.artifacts.paper_full_tex).read_text(encoding="utf-8")
    return len(extract_cited_sentences(text))


def _current_citation_map(state: Any) -> dict[str, Any]:
    current_citation_map = _read_json_if_exists(state.artifacts.citation_map_json)
    return current_citation_map if isinstance(current_citation_map, dict) else {}
