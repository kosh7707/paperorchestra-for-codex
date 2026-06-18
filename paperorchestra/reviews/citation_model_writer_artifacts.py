from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from paperorchestra.core.session import save_session
from paperorchestra.reviews.citation_model_writer_cache_artifacts import _attach_cache_provenance, _write_cache_artifacts
from paperorchestra.reviews.citation_model_writer_trace import _write_review_trace
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


def _write_review_payload(output_path: Path, payload: dict[str, Any]) -> None:
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_human_needed_markdown(output_path: Path, payload: dict[str, Any]) -> None:
    human_needed_markdown = render_citation_support_human_needed_markdown(payload)
    human_needed_markdown_path = output_path.with_name("citation_support_human_needed.md")
    if human_needed_markdown:
        human_needed_markdown_path.write_text(human_needed_markdown, encoding="utf-8")
    else:
        human_needed_markdown_path.unlink(missing_ok=True)
