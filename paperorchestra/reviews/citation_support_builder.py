from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.reviews.citation_items import _heuristic_citation_items
from paperorchestra.reviews.citation_model_cache import _citation_support_provider_identity
from paperorchestra.reviews.citation_support_inputs import CitationReviewInputs, _load_citation_review_inputs
from paperorchestra.reviews.citation_support_model_review import _maybe_run_model_review
from paperorchestra.reviews.citation_support_payload import _citation_support_payload, _evidence_provenance
from paperorchestra.reviews.citation_web_evidence import _citation_support_retrieved_evidence_sha256
from paperorchestra.reviews.source_support import build_source_backed_citation_support_review
from paperorchestra.runtime.provider_base import BaseProvider


def build_citation_support_review(
    cwd: str | Path | None,
    *,
    provider: BaseProvider | None = None,
    evidence_mode: str = "heuristic",
    retrieved_web_evidence: dict[str, Any] | None = None,
    retrieved_web_evidence_sha256: str | None = None,
    retrieved_web_evidence_path: str | None = None,
    progress_stream: Any = None,
    progress_checkpoint_path: str | Path | None = None,
) -> dict[str, Any]:
    if evidence_mode not in {"heuristic", "model", "web", "source"}:
        raise ValueError(f"Unsupported citation evidence mode: {evidence_mode}")
    if evidence_mode == "source":
        return build_source_backed_citation_support_review(cwd, mode=evidence_mode)

    inputs = _load_citation_review_inputs(cwd)
    items = _heuristic_citation_items(inputs.latex, inputs.citation_map)
    provider_identity = _citation_support_provider_identity(provider)
    model_payload, model_trace, items = _maybe_run_model_review(
        provider=provider,
        evidence_mode=evidence_mode,
        items=items,
        manuscript_sha256=inputs.manuscript_sha256,
        citation_map_sha256=inputs.citation_map_sha256,
        provider_identity=provider_identity,
        retrieved_web_evidence=retrieved_web_evidence,
        retrieved_web_evidence_sha256=retrieved_web_evidence_sha256,
        progress_stream=progress_stream,
        progress_checkpoint_path=progress_checkpoint_path,
    )
    research_notes = model_payload.get("research_notes", []) if isinstance(model_payload, dict) else []
    if evidence_mode == "web" and not retrieved_web_evidence_sha256:
        retrieved_web_evidence_sha256 = _citation_support_retrieved_evidence_sha256(items, research_notes)

    return _citation_support_payload(
        state=inputs.state,
        manuscript_sha256=inputs.manuscript_sha256,
        citation_map_sha256=inputs.citation_map_sha256,
        evidence_mode=evidence_mode,
        provider=provider,
        provider_identity=provider_identity,
        retrieved_web_evidence_sha256=retrieved_web_evidence_sha256,
        retrieved_web_evidence_path=retrieved_web_evidence_path,
        items=items,
        research_notes=research_notes,
        model_trace=model_trace,
    )


__all__ = [
    "CitationReviewInputs",
    "_citation_support_payload",
    "_evidence_provenance",
    "_load_citation_review_inputs",
    "_maybe_run_model_review",
    "build_citation_support_review",
]
