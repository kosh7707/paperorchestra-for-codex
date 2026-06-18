from __future__ import annotations

from typing import Any

from paperorchestra.reviews.citation_progress import _citation_progress_cite_label, _emit_citation_progress
from paperorchestra.reviews.citation_web_evidence_payload import (
    _normalized_retrieval_payload,
    _parse_retrieval_response,
)
from paperorchestra.reviews.citation_web_evidence_prompts import _trace_base, _web_evidence_prompts
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


__all__ = [
    "_CHUNK_SIZE",
    "_build_chunked_web_evidence_retrieval",
    "_build_single_web_evidence_retrieval",
    "_build_web_evidence_retrieval",
    "_normalized_retrieval_payload",
    "_parse_retrieval_response",
    "_trace_base",
    "_web_evidence_prompts",
]
