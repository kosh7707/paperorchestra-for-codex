from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _retrieved_web_evidence_for_item_ids(payload: dict[str, Any] | None, item_ids: set[str]) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return payload
    filtered = dict(payload)
    items = payload.get("items")
    if isinstance(items, list):
        filtered["items"] = [item for item in items if isinstance(item, dict) and str(item.get("id")) in item_ids]
    return filtered


def _citation_support_retrieved_evidence_sha256(items: list[dict[str, Any]], research_notes: Any) -> str:
    evidence_payload = {
        "items": [
            {
                "id": item.get("id"),
                "evidence": item.get("evidence") or [],
            }
            for item in items
        ],
        "research_notes": research_notes if isinstance(research_notes, list) else [],
    }
    return hashlib.sha256(json.dumps(evidence_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _retrieved_evidence_file_sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _retrieved_web_evidence_is_reusable(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    trace = payload.get("trace")
    if isinstance(trace, dict):
        if trace.get("parse_error"):
            return False
        chunk_traces = trace.get("chunk_traces")
        if isinstance(chunk_traces, list):
            for chunk_trace in chunk_traces:
                if isinstance(chunk_trace, dict) and chunk_trace.get("parse_error"):
                    return False
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        return False
    total_evidence = 0
    for item in items:
        if not isinstance(item, dict):
            return False
        evidence = item.get("evidence")
        if not isinstance(evidence, list):
            return False
        total_evidence += len(evidence)
    return total_evidence > 0
