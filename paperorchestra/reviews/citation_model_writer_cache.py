from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json
from paperorchestra.reviews.citation_model_cache import (
    _citation_support_cache_dir,
    _citation_support_cache_key,
    _reuse_cached_citation_review,
)
from paperorchestra.reviews.citation_model_writer_types import CitationWriteCacheState
from paperorchestra.reviews.citation_model_writer_web_cache import (
    _ensure_web_evidence,
    _update_web_cache_paths,
    _web_evidence_cache_hit_allowed,
)
from paperorchestra.runtime.provider_base import BaseProvider


def reuse_or_prepare_citation_review_cache(
    *,
    cwd: str | Path | None,
    state: Any,
    output_path: Path,
    provider: BaseProvider | None,
    evidence_mode: str,
    progress_stream: Any = None,
) -> tuple[Path | None, CitationWriteCacheState]:
    cache_state = CitationWriteCacheState()
    if evidence_mode not in {"model", "web"} or provider is None:
        return None, cache_state

    request_cache_key, cache_dir, request_meta = _prepare_cache_request(cwd, state, provider, evidence_mode)
    _prime_cache_paths(cache_state, cache_dir=cache_dir, request_cache_key=request_cache_key, request_meta=request_meta)
    cache_hit_allowed = _web_evidence_cache_hit_allowed(cache_state, request_meta) if evidence_mode == "web" else True

    cached = _try_reuse_cache(
        cwd=cwd,
        state=state,
        output_path=output_path,
        evidence_mode=evidence_mode,
        cache_state=cache_state,
        cache_hit_allowed=cache_hit_allowed,
    )
    if cached is not None:
        return cached, cache_state

    if evidence_mode == "web":
        _ensure_web_evidence(
            state=state,
            provider=provider,
            progress_stream=progress_stream,
            cache_state=cache_state,
        )
        _update_web_cache_paths(cache_state, state=state, provider=provider, cache_dir=cache_dir)
        cached = _try_reuse_cache(
            cwd=cwd,
            state=state,
            output_path=output_path,
            evidence_mode=evidence_mode,
            cache_state=cache_state,
            cache_hit_allowed=cache_state.citation_review_cacheable,
            note_suffix="retrieved-evidence cache",
        )
        if cached is not None:
            return cached, cache_state

    return None, cache_state


def _prepare_cache_request(
    cwd: str | Path | None,
    state: Any,
    provider: BaseProvider,
    evidence_mode: str,
) -> tuple[str, Path, dict[str, Any]]:
    request_cache_key = _citation_support_cache_key(state, provider, evidence_mode)
    cache_dir = _citation_support_cache_dir(cwd)
    cache_dir.mkdir(parents=True, exist_ok=True)
    request_meta_path = cache_dir / f"{request_cache_key}.request.json"
    request_meta = read_json(request_meta_path) if request_meta_path.exists() else {}
    return request_cache_key, cache_dir, request_meta if isinstance(request_meta, dict) else {}


def _prime_cache_paths(
    cache_state: CitationWriteCacheState,
    *,
    cache_dir: Path,
    request_cache_key: str,
    request_meta: dict[str, Any],
) -> None:
    cache_state.cache_key = str(request_meta.get("cache_key_sha256") or request_cache_key)
    cache_state.cache_payload_path = cache_dir / f"{cache_state.cache_key}.json"
    cache_state.cache_trace_path = cache_dir / f"{cache_state.cache_key}.trace.json"
    cache_state.retrieved_web_evidence_path = cache_dir / f"{request_cache_key}.retrieved-evidence.json"
    meta_evidence_path = request_meta.get("retrieved_web_evidence_path")
    if isinstance(meta_evidence_path, str):
        cache_state.retrieved_web_evidence_path = Path(meta_evidence_path)


def _try_reuse_cache(
    *,
    cwd: str | Path | None,
    state: Any,
    output_path: Path,
    evidence_mode: str,
    cache_state: CitationWriteCacheState,
    cache_hit_allowed: bool,
    note_suffix: str = "session cache",
) -> Path | None:
    if not cache_hit_allowed or cache_state.cache_payload_path is None:
        return None
    return _reuse_cached_citation_review(
        cwd=cwd,
        state=state,
        output_path=output_path,
        cache_payload_path=cache_state.cache_payload_path,
        cache_trace_path=cache_state.cache_trace_path,
        evidence_mode=evidence_mode,
        note_suffix=note_suffix,
    )
