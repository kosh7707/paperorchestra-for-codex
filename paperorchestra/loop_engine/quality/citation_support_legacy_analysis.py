from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paperorchestra.loop_engine.quality.citation_support_legacy_proof import (
    _provider_proof_is_trusted,
    _trace_matches_provider_proof,
)
from paperorchestra.loop_engine.quality.policy import CITATION_SUPPORT_STATUSES
from paperorchestra.loop_engine.quality.utils import _file_sha256, _read_json_if_exists
from paperorchestra.manuscript.citations import citation_entry_for_key
from paperorchestra.reviews.citation_evidence import citation_item_has_valid_supporting_evidence
from paperorchestra.reviews.citation_sentences import extract_cited_sentences
from paperorchestra.runtime.provider_registry import get_citation_support_provider
from paperorchestra.runtime.shell_provider import ShellProvider


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


def _expected_web_provider_digest(quality_mode: str) -> str | None:
    if quality_mode != "claim_safe":
        return None
    try:
        expected_provider = get_citation_support_provider("shell", evidence_mode="web")
    except Exception:
        return None
    if not isinstance(expected_provider, ShellProvider):
        return None
    encoded = json.dumps(expected_provider.argv, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _trace_context(provenance: dict[str, Any]) -> dict[str, Any]:
    trace_path = provenance.get("review_trace_path")
    trace_sha = provenance.get("review_trace_sha256")
    actual_trace_sha = _file_sha256(trace_path) if isinstance(trace_path, str) else None
    trace_payload = _read_json_if_exists(trace_path) if isinstance(trace_path, str) else None
    return {"path": trace_path, "sha": trace_sha, "actual_sha": actual_trace_sha, "payload": trace_payload}


def _evidence_counts(
    items: list[dict[str, Any]],
    *,
    payload: dict[str, Any],
    provenance: dict[str, Any],
    current_citation_map: dict[str, Any],
    trace: dict[str, Any],
    expected_web_digest: str | None,
    quality_mode: str,
) -> dict[str, int]:
    counts = {
        "evidence_missing": 0,
        "non_web_supported": 0,
        "untrusted_web_provenance": 0,
        "trace_missing": 0,
        "trace_mismatch": 0,
        "trace_invalid": 0,
    }
    for item in items:
        if item.get("support_status") != "supported":
            continue
        _update_claim_safe_counts(
            counts,
            payload=payload,
            provenance=provenance,
            trace=trace,
            expected_web_digest=expected_web_digest,
            quality_mode=quality_mode,
            items=items,
        )
        item_with_current_entries = _item_with_current_citation_entries(item, current_citation_map)
        if not citation_item_has_valid_supporting_evidence(item_with_current_entries):
            counts["evidence_missing"] += 1
    return counts


def _update_claim_safe_counts(
    counts: dict[str, int],
    *,
    payload: dict[str, Any],
    provenance: dict[str, Any],
    trace: dict[str, Any],
    expected_web_digest: str | None,
    quality_mode: str,
    items: list[dict[str, Any]],
) -> None:
    if quality_mode != "claim_safe":
        return
    if provenance.get("web_search_required") is not True:
        counts["non_web_supported"] += 1
        return
    if not _provider_proof_is_trusted(provenance, expected_web_digest):
        counts["untrusted_web_provenance"] += 1
    if not trace["actual_sha"]:
        counts["trace_missing"] += 1
    elif trace["sha"] != trace["actual_sha"]:
        counts["trace_mismatch"] += 1
    elif not _trace_is_valid(trace["payload"], payload=payload, provenance=provenance, items=items):
        counts["trace_invalid"] += 1


def _trace_is_valid(
    trace_payload: Any,
    *,
    payload: dict[str, Any],
    provenance: dict[str, Any],
    items: list[dict[str, Any]],
) -> bool:
    if not isinstance(trace_payload, dict):
        return False
    expected_items_sha = hashlib.sha256(
        json.dumps(items, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return (
        trace_payload.get("schema_version") == "citation-support-trace/1"
        and trace_payload.get("manuscript_sha256") == payload.get("manuscript_sha256")
        and trace_payload.get("citation_map_sha256") == payload.get("citation_map_sha256")
        and trace_payload.get("review_mode") == "web"
        and trace_payload.get("web_search_required") is True
        and trace_payload.get("provider_command_digest") == provenance.get("provider_command_digest")
        and trace_payload.get("web_search_capable") is True
        and _trace_matches_provider_proof(trace_payload, provenance)
        and trace_payload.get("review_items_sha256") == expected_items_sha
        and bool(trace_payload.get("system_prompt_sha256"))
        and bool(trace_payload.get("user_prompt_sha256"))
        and bool(trace_payload.get("response_sha256"))
    )


def _item_with_current_citation_entries(item: dict[str, Any], current_citation_map: dict[str, Any]) -> dict[str, Any]:
    updated = dict(item)
    entries = []
    for key in item.get("citation_keys") or []:
        entry = citation_entry_for_key(current_citation_map, key)
        entry_payload = dict(entry) if isinstance(entry, dict) else {}
        entry_payload["key"] = key
        entries.append(entry_payload)
    updated["citation_entries"] = entries
    return updated
