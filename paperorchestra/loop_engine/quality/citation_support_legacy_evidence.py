from __future__ import annotations

import hashlib
import json
from typing import Any

from paperorchestra.loop_engine.quality.citation_support_legacy_proof import (
    _provider_proof_is_trusted,
    _trace_matches_provider_proof,
)
from paperorchestra.loop_engine.quality.utils import _file_sha256, _read_json_if_exists
from paperorchestra.manuscript.citations import citation_entry_for_key
from paperorchestra.reviews.citation_evidence import citation_item_has_valid_supporting_evidence
from paperorchestra.runtime.provider_registry import get_citation_support_provider
from paperorchestra.runtime.shell_provider import ShellProvider


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
