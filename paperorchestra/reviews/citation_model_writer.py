from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.session import artifact_path, load_session
from paperorchestra.reviews.citation_model_writer_artifacts import finalize_citation_support_review
from paperorchestra.reviews.citation_model_writer_cache import reuse_or_prepare_citation_review_cache
from paperorchestra.reviews.citation_progress import _citation_progress_path
from paperorchestra.reviews.citation_support_builder import build_citation_support_review
from paperorchestra.runtime.provider_base import BaseProvider


def write_citation_support_review(
    cwd: str | Path | None,
    output_path: str | Path | None = None,
    *,
    provider: BaseProvider | None = None,
    evidence_mode: str = "heuristic",
    progress_stream: Any = None,
    progress_checkpoint_path: str | Path | None = None,
) -> Path:
    state = load_session(cwd)
    path = Path(output_path).resolve() if output_path else artifact_path(cwd, "citation_support_review.json")
    checkpoint_path = _resolve_checkpoint_path(
        output_path=path,
        evidence_mode=evidence_mode,
        progress_stream=progress_stream,
        progress_checkpoint_path=progress_checkpoint_path,
    )
    cached, cache_state = reuse_or_prepare_citation_review_cache(
        cwd=cwd,
        state=state,
        output_path=path,
        provider=provider,
        evidence_mode=evidence_mode,
        progress_stream=progress_stream,
    )
    if cached is not None:
        return cached

    payload = build_citation_support_review(
        cwd,
        provider=provider,
        evidence_mode=evidence_mode,
        retrieved_web_evidence=cache_state.retrieved_web_evidence,
        retrieved_web_evidence_sha256=cache_state.retrieved_web_evidence_sha256,
        retrieved_web_evidence_path=str(cache_state.retrieved_web_evidence_path)
        if cache_state.retrieved_web_evidence_path is not None
        else None,
        progress_stream=progress_stream,
        progress_checkpoint_path=checkpoint_path,
    )
    return finalize_citation_support_review(
        cwd=cwd,
        state=state,
        output_path=path,
        payload=payload,
        provider=provider,
        evidence_mode=evidence_mode,
        cache_state=cache_state,
        progress_checkpoint_path=checkpoint_path,
    )


def _resolve_checkpoint_path(
    *,
    output_path: Path,
    evidence_mode: str,
    progress_stream: Any,
    progress_checkpoint_path: str | Path | None,
) -> Path | None:
    if progress_checkpoint_path is not None:
        return Path(progress_checkpoint_path).resolve()
    if progress_stream is not None and evidence_mode in {"model", "web"}:
        return _citation_progress_path(output_path)
    return None
