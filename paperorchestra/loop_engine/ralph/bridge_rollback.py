from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paperorchestra.core.session import load_session
from paperorchestra.loop_engine.ralph.state import (
    _file_content_snapshot,
    _restore_session_mutation_snapshot,
    _session_mutation_snapshot,
    atomic_write_text,
    clear_pending_manuscript_write,
)


@dataclass(frozen=True)
class QaLoopRollbackContext:
    paper_path: Path | None
    original_paper: str | None
    mutation_snapshot: dict[str, Any]
    citation_review_snapshot: dict[str, Any]
    citation_trace_snapshot: dict[str, Any]


def capture_qa_loop_rollback_context(cwd: str | Path | None) -> QaLoopRollbackContext:
    state_for_rollback = load_session(cwd)
    paper_path = (
        Path(state_for_rollback.artifacts.paper_full_tex)
        if state_for_rollback.artifacts.paper_full_tex
        else None
    )
    original_paper = paper_path.read_text(encoding="utf-8") if paper_path and paper_path.exists() else None
    citation_review_path = paper_path.resolve().parent / "citation_support_review.json" if paper_path else None
    citation_trace_path = paper_path.resolve().parent / "citation_support_review.trace.json" if paper_path else None
    return QaLoopRollbackContext(
        paper_path=paper_path,
        original_paper=original_paper,
        mutation_snapshot=_session_mutation_snapshot(state_for_rollback),
        citation_review_snapshot=_file_content_snapshot(citation_review_path),
        citation_trace_snapshot=_file_content_snapshot(citation_trace_path),
    )


def restore_candidate_after_exception(
    *,
    cwd: str | Path | None,
    rollback: QaLoopRollbackContext,
    citation_candidate_applied: bool,
) -> None:
    if not citation_candidate_applied or not rollback.paper_path or rollback.original_paper is None:
        return
    atomic_write_text(rollback.paper_path, rollback.original_paper)
    clear_pending_manuscript_write(cwd, status="restored", reason="qa_loop_candidate_exception")
    _restore_session_mutation_snapshot(cwd, rollback.mutation_snapshot)
