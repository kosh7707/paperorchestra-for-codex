from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from paperorchestra.core.session import save_session
from paperorchestra.reviews.citation_model_cache import _citation_support_cache_dir, _citation_support_cache_key
from paperorchestra.reviews.citation_model_writer_types import CitationWriteCacheState
from paperorchestra.reviews.source_support import render_citation_support_human_needed_markdown
from paperorchestra.runtime.provider_base import BaseProvider


def finalize_citation_support_review(
    *,
    cwd: str | Path | None,
    state: Any,
    output_path: Path,
    payload: dict[str, Any],
    provider: BaseProvider | None,
    evidence_mode: str,
    cache_state: CitationWriteCacheState,
    progress_checkpoint_path: Path | None,
) -> Path:
    _attach_progress_checkpoint(payload, progress_checkpoint_path)
    _attach_cache_provenance(
        cwd=cwd,
        state=state,
        provider=provider,
        evidence_mode=evidence_mode,
        payload=payload,
        cache_state=cache_state,
    )
    _write_review_trace(output_path, payload)
    _write_review_payload(output_path, payload)
    _write_human_needed_markdown(output_path, payload)
    _write_cache_artifacts(
        cwd=cwd,
        state=state,
        output_path=output_path,
        payload=payload,
        provider=provider,
        evidence_mode=evidence_mode,
        cache_state=cache_state,
    )
    state.notes.append(f"Citation-support critic artifact recorded: {output_path.name} (mode={evidence_mode})")
    save_session(cwd, state)
    return output_path


def _attach_progress_checkpoint(payload: dict[str, Any], checkpoint_path: Path | None) -> None:
    if checkpoint_path is None:
        return
    provenance = payload.setdefault("evidence_provenance", {})
    provenance["progress_checkpoint_path"] = str(checkpoint_path)
    if checkpoint_path.exists():
        provenance["progress_checkpoint_sha256"] = hashlib.sha256(checkpoint_path.read_bytes()).hexdigest()


def _attach_cache_provenance(
    *,
    cwd: str | Path | None,
    state: Any,
    provider: BaseProvider | None,
    evidence_mode: str,
    payload: dict[str, Any],
    cache_state: CitationWriteCacheState,
) -> None:
    if not cache_state.cache_key or not cache_state.citation_review_cacheable:
        return
    provenance = payload.setdefault("evidence_provenance", {})
    evidence_sha = provenance.get("retrieved_web_evidence_sha256") if evidence_mode == "web" else None
    if evidence_mode == "web":
        cache_state.cache_key = _citation_support_cache_key(
            state,
            provider,
            evidence_mode,
            retrieved_web_evidence_sha256=str(evidence_sha) if evidence_sha else None,
        )
    cache_state.cache_payload_path = _citation_support_cache_dir(cwd) / f"{cache_state.cache_key}.json"
    cache_state.cache_trace_path = _citation_support_cache_dir(cwd) / f"{cache_state.cache_key}.trace.json"
    provenance["cache_key_sha256"] = cache_state.cache_key
    provenance["cache_scope"] = "session_id"
    provenance["evidence_identity_source"] = (
        "pre_review_retrieved_evidence_artifact" if evidence_sha else "not_applicable"
    )


def _write_review_trace(output_path: Path, payload: dict[str, Any]) -> None:
    trace_payload = payload.pop("_trace", None)
    if not isinstance(trace_payload, dict):
        return
    trace_payload = _trace_payload_with_review_identity(trace_payload, payload)
    trace_path = output_path.with_name(output_path.stem + ".trace.json")
    trace_text = json.dumps(trace_payload, indent=2, ensure_ascii=False) + "\n"
    trace_path.write_text(trace_text, encoding="utf-8")
    trace_sha = hashlib.sha256(trace_text.encode("utf-8")).hexdigest()
    payload.setdefault("evidence_provenance", {})["review_trace_path"] = str(trace_path)
    payload.setdefault("evidence_provenance", {})["review_trace_sha256"] = trace_sha


def _trace_payload_with_review_identity(trace_payload: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    provenance = payload.get("evidence_provenance") or {}
    enriched = dict(trace_payload)
    enriched.update(
        {
            "manuscript_sha256": payload.get("manuscript_sha256"),
            "citation_map_sha256": payload.get("citation_map_sha256"),
            "review_mode": payload.get("review_mode"),
            "provider_command_digest": provenance.get("provider_command_digest"),
            "provider_capability_proof": provenance.get("provider_capability_proof"),
            "provider_contract_path": provenance.get("provider_contract_path"),
            "provider_contract_sha256": provenance.get("provider_contract_sha256"),
            "provider_wrapper_path": provenance.get("provider_wrapper_path"),
            "provider_wrapper_sha256": provenance.get("provider_wrapper_sha256"),
            "provider_wrapper_mode": provenance.get("provider_wrapper_mode"),
            "web_search_capable": provenance.get("web_search_capable"),
            "review_items_sha256": hashlib.sha256(
                json.dumps(payload.get("items") or [], sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest(),
        }
    )
    return enriched


def _write_review_payload(output_path: Path, payload: dict[str, Any]) -> None:
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_human_needed_markdown(output_path: Path, payload: dict[str, Any]) -> None:
    human_needed_markdown = render_citation_support_human_needed_markdown(payload)
    human_needed_markdown_path = output_path.with_name("citation_support_human_needed.md")
    if human_needed_markdown:
        human_needed_markdown_path.write_text(human_needed_markdown, encoding="utf-8")
    else:
        human_needed_markdown_path.unlink(missing_ok=True)


def _write_cache_artifacts(
    *,
    cwd: str | Path | None,
    state: Any,
    output_path: Path,
    payload: dict[str, Any],
    provider: BaseProvider | None,
    evidence_mode: str,
    cache_state: CitationWriteCacheState,
) -> None:
    if not cache_state.citation_review_cacheable or cache_state.cache_payload_path is None:
        return
    cache_state.cache_payload_path.write_text(output_path.read_text(encoding="utf-8"), encoding="utf-8")
    if evidence_mode in {"model", "web"} and provider is not None:
        _write_cache_request_meta(
            cwd=cwd,
            state=state,
            payload=payload,
            provider=provider,
            evidence_mode=evidence_mode,
        )
    trace_path_value = (payload.get("evidence_provenance") or {}).get("review_trace_path")
    if (
        cache_state.cache_trace_path is not None
        and isinstance(trace_path_value, str)
        and Path(trace_path_value).exists()
    ):
        shutil.copy2(trace_path_value, cache_state.cache_trace_path)


def _write_cache_request_meta(
    *,
    cwd: str | Path | None,
    state: Any,
    payload: dict[str, Any],
    provider: BaseProvider,
    evidence_mode: str,
) -> None:
    request_cache_key = _citation_support_cache_key(state, provider, evidence_mode)
    request_meta_path = _citation_support_cache_dir(cwd) / f"{request_cache_key}.request.json"
    provenance = payload.get("evidence_provenance") or {}
    request_meta_path.write_text(
        json.dumps(
            {
                "schema_version": "citation-support-cache-request/1",
                "cache_scope": "session_id",
                "cache_key_sha256": provenance.get("cache_key_sha256"),
                "retrieved_web_evidence_sha256": provenance.get("retrieved_web_evidence_sha256"),
                "retrieved_web_evidence_path": provenance.get("retrieved_web_evidence_path"),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
