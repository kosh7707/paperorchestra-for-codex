from __future__ import annotations

import hashlib
import json
from typing import Any

from paperorchestra.core.io import ExtractionError, extract_json
from paperorchestra.reviews.citation_evidence import _clean_evidence
from paperorchestra.reviews.citation_progress import _citation_progress_cite_label, _emit_citation_progress
from paperorchestra.runtime.provider_base import BaseProvider, CompletionRequest

_CHUNK_SIZE = 8


def _build_web_evidence_retrieval(
    *,
    provider: BaseProvider,
    items: list[dict[str, Any]],
    progress_stream: Any = None,
) -> dict[str, Any]:
    if len(items) > _CHUNK_SIZE:
        return _build_chunked_web_evidence_retrieval(provider=provider, items=items, progress_stream=progress_stream)
    return _build_single_web_evidence_retrieval(provider=provider, items=items, progress_stream=progress_stream)


def _build_chunked_web_evidence_retrieval(
    *,
    provider: BaseProvider,
    items: list[dict[str, Any]],
    progress_stream: Any = None,
) -> dict[str, Any]:
    merged_items: list[dict[str, Any]] = []
    research_notes: list[str] = []
    chunk_traces: list[dict[str, Any]] = []
    for start in range(0, len(items), _CHUNK_SIZE):
        chunk = items[start : start + _CHUNK_SIZE]
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
            "chunk_size": _CHUNK_SIZE,
            "chunk_count": len(chunk_traces),
            "chunk_traces": chunk_traces,
            "web_search_required": True,
        },
    }


def _build_single_web_evidence_retrieval(
    *,
    provider: BaseProvider,
    items: list[dict[str, Any]],
    progress_stream: Any = None,
) -> dict[str, Any]:
    if items:
        _emit_citation_progress(
            progress_stream,
            f"retrieving 1-{len(items)}/{len(items)} cite={_citation_progress_cite_label(items[0])}",
        )
    system_prompt, user_prompt = _web_evidence_prompts(items)
    response = provider.complete(CompletionRequest(system_prompt=system_prompt, user_prompt=user_prompt))
    if items:
        _emit_citation_progress(progress_stream, f"retrieved 1-{len(items)}/{len(items)}")
    trace_base = _trace_base(system_prompt, user_prompt, response)
    payload = _parse_retrieval_response(response, trace_base)
    return _normalized_retrieval_payload(items, payload, trace_base)


def _web_evidence_prompts(items: list[dict[str, Any]]) -> tuple[str, str]:
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
    return system_prompt, user_prompt


def _trace_base(system_prompt: str, user_prompt: str, response: str) -> dict[str, Any]:
    return {
        "schema_version": "citation-support-retrieval-trace/1",
        "system_prompt_sha256": hashlib.sha256(system_prompt.encode("utf-8")).hexdigest(),
        "user_prompt_sha256": hashlib.sha256(user_prompt.encode("utf-8")).hexdigest(),
        "response_sha256": hashlib.sha256(response.encode("utf-8")).hexdigest(),
        "web_search_required": True,
    }


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
