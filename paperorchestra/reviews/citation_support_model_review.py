from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.reviews.citation_model_merge import _merge_model_citation_review
from paperorchestra.reviews.citation_model_progress_review import _build_model_citation_review_with_progress
from paperorchestra.reviews.citation_model_prompt import _build_model_citation_review
from paperorchestra.runtime.provider_base import BaseProvider


def _maybe_run_model_review(
    *,
    provider: BaseProvider | None,
    evidence_mode: str,
    items: list[dict[str, Any]],
    manuscript_sha256: str,
    citation_map_sha256: str | None,
    provider_identity: dict[str, Any],
    retrieved_web_evidence: dict[str, Any] | None,
    retrieved_web_evidence_sha256: str | None,
    progress_stream: Any,
    progress_checkpoint_path: str | Path | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[dict[str, Any]]]:
    if evidence_mode not in {"model", "web"}:
        return None, None, items
    if provider is None:
        raise ValueError(f"evidence_mode={evidence_mode!r} requires a provider.")
    if progress_stream is not None or progress_checkpoint_path is not None:
        model_payload = _build_model_citation_review_with_progress(
            provider=provider,
            items=items,
            web_search_required=evidence_mode == "web",
            evidence_mode=evidence_mode,
            manuscript_sha256=manuscript_sha256,
            citation_map_sha256=citation_map_sha256,
            provider_identity=provider_identity,
            retrieved_web_evidence=retrieved_web_evidence if evidence_mode == "web" else None,
            retrieved_web_evidence_sha256=retrieved_web_evidence_sha256 if evidence_mode == "web" else None,
            progress_stream=progress_stream,
            progress_checkpoint_path=Path(progress_checkpoint_path).resolve()
            if progress_checkpoint_path is not None
            else None,
        )
        model_trace = model_payload.pop("_trace", None)
        reviewed_items = model_payload.get("items") if isinstance(model_payload.get("items"), list) else items
        return model_payload, model_trace, reviewed_items

    model_payload = _build_model_citation_review(
        provider=provider,
        items=items,
        web_search_required=evidence_mode == "web",
        retrieved_web_evidence=retrieved_web_evidence if evidence_mode == "web" else None,
    )
    model_trace = model_payload.pop("_trace", None)
    return model_payload, model_trace, _merge_model_citation_review(items, model_payload)
