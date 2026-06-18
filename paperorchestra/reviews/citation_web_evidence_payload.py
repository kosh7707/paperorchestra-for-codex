from __future__ import annotations

import json
from typing import Any

from paperorchestra.core.io import ExtractionError, extract_json
from paperorchestra.reviews.citation_evidence import _clean_evidence


def _parse_retrieval_response(response: str, trace_base: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = extract_json(response)
    except (ExtractionError, json.JSONDecodeError, ValueError) as exc:
        return {
            "items": [],
            "research_notes": [f"Citation-support evidence retrieval returned malformed JSON: {type(exc).__name__}."],
            "_trace": {
                **trace_base,
                "parse_error": type(exc).__name__,
                "parse_error_message": str(exc),
            },
        }
    if not isinstance(payload, dict):
        payload = {"items": [], "research_notes": ["Citation-support evidence retrieval returned non-object JSON."]}
    payload["_trace"] = trace_base
    return payload


def _normalized_retrieval_payload(
    items: list[dict[str, Any]],
    payload: dict[str, Any],
    trace_base: dict[str, Any],
) -> dict[str, Any]:
    raw_by_id = {str(item.get("id")): item for item in payload.get("items", []) if isinstance(item, dict)}
    normalized_items: list[dict[str, Any]] = []
    for item in items:
        raw = raw_by_id.get(item["id"], {})
        normalized_items.append(
            {
                "id": item["id"],
                "sentence": item["sentence"],
                "citation_keys": item["citation_keys"],
                "citation_entries": item["citation_entries"],
                "claim_type": item["claim_type"],
                "evidence": _clean_evidence(raw.get("evidence") if isinstance(raw, dict) else []),
            }
        )
    research_notes = payload.get("research_notes") if isinstance(payload.get("research_notes"), list) else []
    return {
        "schema_version": "citation-support-retrieved-evidence/1",
        "items": normalized_items,
        "research_notes": research_notes,
        "trace": payload.get("_trace") if isinstance(payload.get("_trace"), dict) else trace_base,
    }
