from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from paperorchestra.core.io import ExtractionError, extract_json
from paperorchestra.reviews.citation_evidence import _clean_evidence
from paperorchestra.reviews.citation_progress import _citation_progress_cite_label, _emit_citation_progress
from paperorchestra.runtime.providers import BaseProvider, CompletionRequest


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


def _build_web_evidence_retrieval(
    *,
    provider: BaseProvider,
    items: list[dict[str, Any]],
    progress_stream: Any = None,
) -> dict[str, Any]:
    chunk_size = 8
    if len(items) > chunk_size:
        merged_items: list[dict[str, Any]] = []
        research_notes: list[str] = []
        chunk_traces: list[dict[str, Any]] = []
        for start in range(0, len(items), chunk_size):
            chunk = items[start : start + chunk_size]
            end = start + len(chunk)
            _emit_citation_progress(
                progress_stream,
                f"retrieving {start + 1}-{end}/{len(items)} cite={_citation_progress_cite_label(chunk[0])}",
            )
            chunk_payload = _build_web_evidence_retrieval(provider=provider, items=chunk)
            _emit_citation_progress(progress_stream, f"retrieved {start + 1}-{end}/{len(items)}")
            merged_items.extend(chunk_payload.get("items") if isinstance(chunk_payload.get("items"), list) else [])
            if isinstance(chunk_payload.get("research_notes"), list):
                research_notes.extend(str(note) for note in chunk_payload.get("research_notes", []))
            if isinstance(chunk_payload.get("trace"), dict):
                trace = dict(chunk_payload["trace"])
                trace["chunk_start"] = start
                trace["chunk_size"] = len(chunk)
                chunk_traces.append(trace)
        return {
            "schema_version": "citation-support-retrieved-evidence/1",
            "items": merged_items,
            "research_notes": research_notes,
            "trace": {
                "schema_version": "citation-support-retrieval-trace/1",
                "chunked": True,
                "chunk_size": chunk_size,
                "chunk_count": len(chunk_traces),
                "chunk_traces": chunk_traces,
                "web_search_required": True,
            },
        }

    if items:
        _emit_citation_progress(
            progress_stream,
            f"retrieving 1-{len(items)}/{len(items)} cite={_citation_progress_cite_label(items[0])}",
        )
    review_items = [
        {
            "id": item["id"],
            "sentence": item["sentence"],
            "citation_keys": item["citation_keys"],
            "citation_entries": item["citation_entries"],
            "claim_type": item["claim_type"],
        }
        for item in items
    ]
    system_prompt = """
You are PaperOrchestra's citation-support evidence retriever.
Your job is to collect source evidence only, before any verdict is assigned.

Rules:
- Use web/source lookup if available.
- Do not decide final support_status.
- Do not rewrite manuscript prose.
- Do not invent bibliographic metadata, URLs, source titles, or evidence.
- Return JSON only.
""".strip()
    user_prompt = f"""
Collect cited-source evidence for these manuscript sentences.

Return JSON with exactly these top-level keys:
- items: array, one object per input id
- research_notes: array of strings

Each item must contain:
- id
- evidence: array of objects with citation_key, source_title, url, evidence_quote_or_summary, supports_claim

Input:
{json.dumps({"items": review_items}, indent=2, ensure_ascii=False)}
""".strip()
    response = provider.complete(CompletionRequest(system_prompt=system_prompt, user_prompt=user_prompt))
    if items:
        _emit_citation_progress(progress_stream, f"retrieved 1-{len(items)}/{len(items)}")
    trace_base = {
        "schema_version": "citation-support-retrieval-trace/1",
        "system_prompt_sha256": hashlib.sha256(system_prompt.encode("utf-8")).hexdigest(),
        "user_prompt_sha256": hashlib.sha256(user_prompt.encode("utf-8")).hexdigest(),
        "response_sha256": hashlib.sha256(response.encode("utf-8")).hexdigest(),
        "web_search_required": True,
    }
    try:
        payload = extract_json(response)
    except (ExtractionError, json.JSONDecodeError, ValueError) as exc:
        payload = {
            "items": [],
            "research_notes": [
                f"Citation-support evidence retrieval returned malformed JSON: {type(exc).__name__}."
            ],
            "_trace": {
                **trace_base,
                "parse_error": type(exc).__name__,
                "parse_error_message": str(exc),
            },
        }
    else:
        if not isinstance(payload, dict):
            payload = {"items": [], "research_notes": ["Citation-support evidence retrieval returned non-object JSON."]}
        payload["_trace"] = trace_base

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
