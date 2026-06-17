from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.reviews.citation_model_merge import _merge_model_citation_review
from paperorchestra.reviews.citation_model_prompt import _build_model_citation_review
from paperorchestra.reviews.citation_progress import (
    _append_citation_progress_checkpoint,
    _citation_progress_cite_label,
    _citation_progress_claim_input_sha256,
    _citation_progress_provider_identity_sha256,
    _emit_citation_progress,
    _load_citation_progress_checkpoint,
)
from paperorchestra.reviews.citation_web_evidence import _retrieved_web_evidence_for_item_ids
from paperorchestra.runtime.providers import BaseProvider


def _build_model_citation_review_with_progress(
    *,
    provider: BaseProvider,
    items: list[dict[str, Any]],
    web_search_required: bool,
    evidence_mode: str,
    manuscript_sha256: str,
    citation_map_sha256: str | None,
    provider_identity: dict[str, Any],
    retrieved_web_evidence: dict[str, Any] | None = None,
    retrieved_web_evidence_sha256: str | None = None,
    progress_stream: Any = None,
    progress_checkpoint_path: Path | None = None,
) -> dict[str, Any]:
    completed = _load_citation_progress_checkpoint(
        progress_checkpoint_path,
        manuscript_sha256=manuscript_sha256,
        citation_map_sha256=citation_map_sha256,
        evidence_mode=evidence_mode,
        provider_identity=provider_identity,
        retrieved_web_evidence_sha256=retrieved_web_evidence_sha256,
        items=items,
    )
    provider_identity_sha256 = _citation_progress_provider_identity_sha256(provider_identity)
    merged_items: list[dict[str, Any]] = []
    research_notes: list[str] = []
    claim_traces: list[dict[str, Any]] = []
    reused_claims = 0
    claim_count = len(items)
    for index, item in enumerate(items, start=1):
        claim_id = str(item.get("id"))
        cite_label = _citation_progress_cite_label(item)
        cached_item = completed.get(claim_id)
        if cached_item is not None:
            reused_claims += 1
            _emit_citation_progress(progress_stream, f"reusing {index}/{claim_count} cite={cite_label} id={claim_id}")
            merged_items.append(cached_item)
            continue

        _emit_citation_progress(progress_stream, f"checking {index}/{claim_count} cite={cite_label} id={claim_id}")
        item_retrieved_web_evidence = _retrieved_web_evidence_for_item_ids(retrieved_web_evidence, {claim_id})
        model_payload = _build_model_citation_review(
            provider=provider,
            items=[item],
            web_search_required=web_search_required,
            retrieved_web_evidence=item_retrieved_web_evidence if web_search_required else None,
        )
        trace = model_payload.pop("_trace", None)
        if isinstance(trace, dict):
            trace = dict(trace)
            trace["claim_id"] = claim_id
            trace["claim_index"] = index
            claim_traces.append(trace)
        if isinstance(model_payload.get("research_notes"), list):
            research_notes.extend(str(note) for note in model_payload.get("research_notes", []))
        merged = _merge_model_citation_review([item], model_payload)
        merged_item = merged[0] if merged else dict(item)
        merged_items.append(merged_item)
        _append_citation_progress_checkpoint(
            progress_checkpoint_path,
            {
                "schema_version": "citation-support-progress-checkpoint/1",
                "event": "checked",
                "manuscript_sha256": manuscript_sha256,
                "citation_map_sha256": citation_map_sha256,
                "evidence_mode": evidence_mode,
                "provider_identity_sha256": provider_identity_sha256,
                "retrieved_web_evidence_sha256": retrieved_web_evidence_sha256,
                "claim_id": claim_id,
                "claim_index": index,
                "claim_count": claim_count,
                "citation_keys": item.get("citation_keys") or [],
                "claim_input_sha256": _citation_progress_claim_input_sha256(item),
                "item": merged_item,
            },
        )
        _emit_citation_progress(progress_stream, f"checked {index}/{claim_count} cite={cite_label} id={claim_id}")

    return {
        "items": merged_items,
        "research_notes": research_notes,
        "_trace": {
            "schema_version": "citation-support-trace/1",
            "chunked": True,
            "claim_count": claim_count,
            "reused_claims": reused_claims,
            "checked_claims": claim_count - reused_claims,
            "web_search_required": web_search_required,
            "claim_traces": claim_traces,
            "progress_checkpoint_path": str(progress_checkpoint_path) if progress_checkpoint_path is not None else None,
        },
    }
