from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json
from paperorchestra.core.session import load_session
from paperorchestra.reviews.citation_items import _heuristic_citation_items, _summary_from_items
from paperorchestra.reviews.citation_model_cache import _citation_support_provider_identity
from paperorchestra.reviews.citation_model_merge import _merge_model_citation_review
from paperorchestra.reviews.citation_model_progress_review import _build_model_citation_review_with_progress
from paperorchestra.reviews.citation_model_prompt import _build_model_citation_review
from paperorchestra.reviews.citation_web_evidence import _citation_support_retrieved_evidence_sha256
from paperorchestra.reviews.source_support import build_source_backed_citation_support_review
from paperorchestra.runtime.providers import BaseProvider


@dataclass(frozen=True)
class CitationReviewInputs:
    state: Any
    latex: str
    manuscript_sha256: str
    citation_map: dict[str, Any]
    citation_map_sha256: str | None


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


def _load_citation_review_inputs(cwd: str | Path | None) -> CitationReviewInputs:
    state = load_session(cwd)
    if not state.artifacts.paper_full_tex:
        raise ValueError("Need paper.full.tex before citation support review.")
    paper_path = Path(state.artifacts.paper_full_tex)
    latex = paper_path.read_text(encoding="utf-8")
    manuscript_sha256 = hashlib.sha256(paper_path.read_bytes()).hexdigest()
    citation_map = read_json(state.artifacts.citation_map_json) if state.artifacts.citation_map_json else {}
    citation_map_sha256 = None
    if state.artifacts.citation_map_json and Path(state.artifacts.citation_map_json).exists():
        citation_map_sha256 = hashlib.sha256(Path(state.artifacts.citation_map_json).read_bytes()).hexdigest()
    return CitationReviewInputs(
        state=state,
        latex=latex,
        manuscript_sha256=manuscript_sha256,
        citation_map=citation_map,
        citation_map_sha256=citation_map_sha256,
    )


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


def _citation_support_payload(
    *,
    state: Any,
    manuscript_sha256: str,
    citation_map_sha256: str | None,
    evidence_mode: str,
    provider: BaseProvider | None,
    provider_identity: dict[str, Any],
    retrieved_web_evidence_sha256: str | None,
    retrieved_web_evidence_path: str | None,
    items: list[dict[str, Any]],
    research_notes: Any,
    model_trace: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "schema_version": "citation-support-review/2",
        "session_id": state.session_id,
        "manuscript_sha256": manuscript_sha256,
        "citation_map_sha256": citation_map_sha256,
        "review_mode": evidence_mode,
        "evidence_provenance": _evidence_provenance(
            evidence_mode=evidence_mode,
            provider=provider,
            provider_identity=provider_identity,
            retrieved_web_evidence_sha256=retrieved_web_evidence_sha256,
            retrieved_web_evidence_path=retrieved_web_evidence_path,
        ),
        "claims_checked": len(items),
        "summary": _summary_from_items(items),
        "items": items,
        "research_notes": research_notes,
        "_trace": model_trace,
    }


def _evidence_provenance(
    *,
    evidence_mode: str,
    provider: BaseProvider | None,
    provider_identity: dict[str, Any],
    retrieved_web_evidence_sha256: str | None,
    retrieved_web_evidence_path: str | None,
) -> dict[str, Any]:
    return {
        "mode": evidence_mode,
        "semantic_scholar_required": False,
        "web_search_required": evidence_mode == "web",
        "model_review_used": evidence_mode in {"model", "web"},
        "provider_name": getattr(provider, "name", None) if provider is not None else None,
        "provider_command_digest": provider_identity.get("provider_command_digest"),
        "provider_class": provider_identity.get("provider_class"),
        "provider_argv": provider_identity.get("provider_argv"),
        "provider_capability_proof": provider_identity.get("provider_capability_proof"),
        "provider_contract_path": provider_identity.get("provider_contract_path"),
        "provider_contract_sha256": provider_identity.get("provider_contract_sha256"),
        "provider_wrapper_path": provider_identity.get("provider_wrapper_path"),
        "provider_wrapper_sha256": provider_identity.get("provider_wrapper_sha256"),
        "provider_wrapper_mode": provider_identity.get("provider_wrapper_mode"),
        "provider_wrapper_exec_argv_prefix": provider_identity.get("provider_wrapper_exec_argv_prefix"),
        "web_search_capable": bool(provider_identity.get("web_search_capable")),
        "claim_support_not_metadata_lookup": True,
        "retrieved_web_evidence_sha256": retrieved_web_evidence_sha256,
        "retrieved_web_evidence_path": retrieved_web_evidence_path,
    }


__all__ = ["build_citation_support_review"]
