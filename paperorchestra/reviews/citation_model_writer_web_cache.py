from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json
from paperorchestra.reviews.citation_items import _heuristic_citation_items
from paperorchestra.reviews.citation_model_cache import _citation_support_cache_key
from paperorchestra.reviews.citation_model_writer_types import CitationWriteCacheState
from paperorchestra.reviews.citation_web_evidence import (
    _build_web_evidence_retrieval,
    _retrieved_evidence_file_sha256,
    _retrieved_web_evidence_is_reusable,
)
from paperorchestra.runtime.provider_base import BaseProvider


def _web_evidence_cache_hit_allowed(
    cache_state: CitationWriteCacheState,
    request_meta: dict[str, Any],
) -> bool:
    evidence_path = cache_state.retrieved_web_evidence_path
    if evidence_path is None:
        return False
    meta_evidence_sha = str(request_meta.get("retrieved_web_evidence_sha256") or "")
    actual_evidence_sha = _retrieved_evidence_file_sha256(evidence_path)
    cache_hit_allowed = bool(meta_evidence_sha and actual_evidence_sha and meta_evidence_sha == actual_evidence_sha)
    if cache_hit_allowed and evidence_path.exists():
        existing_evidence = read_json(evidence_path)
        if not _retrieved_web_evidence_is_reusable(existing_evidence):
            evidence_path.unlink(missing_ok=True)
            mark_citation_review_uncacheable(cache_state)
            return False
    return cache_hit_allowed


def _ensure_web_evidence(
    *,
    state: Any,
    provider: BaseProvider,
    progress_stream: Any,
    cache_state: CitationWriteCacheState,
) -> None:
    evidence_path = cache_state.retrieved_web_evidence_path
    assert evidence_path is not None
    if evidence_path.exists():
        cache_state.retrieved_web_evidence = read_json(evidence_path)
        if not _retrieved_web_evidence_is_reusable(cache_state.retrieved_web_evidence):
            evidence_path.unlink(missing_ok=True)
            cache_state.retrieved_web_evidence = None
            mark_citation_review_uncacheable(cache_state)
    if cache_state.retrieved_web_evidence is None:
        cache_state.retrieved_web_evidence = _retrieve_web_evidence(
            state=state,
            provider=provider,
            progress_stream=progress_stream,
        )
        evidence_path.write_text(
            json.dumps(cache_state.retrieved_web_evidence, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        cache_state.citation_review_cacheable = _retrieved_web_evidence_is_reusable(cache_state.retrieved_web_evidence)
        if not cache_state.citation_review_cacheable:
            mark_citation_review_uncacheable(cache_state)
    cache_state.retrieved_web_evidence_sha256 = _retrieved_evidence_file_sha256(evidence_path)


def _retrieve_web_evidence(
    *,
    state: Any,
    provider: BaseProvider,
    progress_stream: Any,
) -> dict[str, Any]:
    latex = Path(state.artifacts.paper_full_tex).read_text(encoding="utf-8")
    citation_map = read_json(state.artifacts.citation_map_json) if state.artifacts.citation_map_json else {}
    retrieval_items = _heuristic_citation_items(latex, citation_map)
    return _build_web_evidence_retrieval(
        provider=provider,
        items=retrieval_items,
        progress_stream=progress_stream,
    )


def _update_web_cache_paths(
    cache_state: CitationWriteCacheState,
    *,
    state: Any,
    provider: BaseProvider,
    cache_dir: Path,
) -> None:
    if not cache_state.citation_review_cacheable:
        return
    cache_state.cache_key = _citation_support_cache_key(
        state,
        provider,
        "web",
        retrieved_web_evidence_sha256=cache_state.retrieved_web_evidence_sha256,
    )
    cache_state.cache_payload_path = cache_dir / f"{cache_state.cache_key}.json"
    cache_state.cache_trace_path = cache_dir / f"{cache_state.cache_key}.trace.json"


def mark_citation_review_uncacheable(cache_state: CitationWriteCacheState) -> None:
    cache_state.citation_review_cacheable = False
    cache_state.cache_key = None
    cache_state.cache_payload_path = None
    cache_state.cache_trace_path = None
