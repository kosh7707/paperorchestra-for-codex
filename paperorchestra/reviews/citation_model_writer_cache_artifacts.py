from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from paperorchestra.reviews.citation_model_cache import _citation_support_cache_dir, _citation_support_cache_key
from paperorchestra.reviews.citation_model_writer_types import CitationWriteCacheState
from paperorchestra.runtime.provider_base import BaseProvider


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
    provenance["evidence_identity_source"] = "pre_review_retrieved_evidence_artifact" if evidence_sha else "not_applicable"


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
    if cache_state.cache_trace_path is not None and isinstance(trace_path_value, str) and Path(trace_path_value).exists():
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
