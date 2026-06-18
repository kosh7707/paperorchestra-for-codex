from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.ralph.action_dispatch_types import (
    QaLoopActionDispatchContext,
    _QaLoopActionDispatchState,
)
from paperorchestra.loop_engine.ralph.artifacts import (
    _refresh_citation_integrity_for_current_manuscript,
    _try_rebuild_bib_for_citation_quality,
)
from paperorchestra.reviews.citation_model_writer import write_citation_support_review


def handle_citation_support_review(
    code: str,
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
    state: _QaLoopActionDispatchState,
) -> bool:
    review_path = write_citation_support_review(
        context.cwd,
        provider=context.citation_provider,
        evidence_mode=context.citation_evidence_mode,
    )
    execution["actions_attempted"].append({"code": code, "handler": "critique_citations", "path": str(review_path)})
    return True


def handle_citation_quality_refresh(
    code: str,
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
    state: _QaLoopActionDispatchState,
) -> bool:
    bibtex_rebuild = (
        _try_rebuild_bib_for_citation_quality(context.cwd)
        if code == "critical_weak_reference_identity"
        else None
    )
    review_path = write_citation_support_review(
        context.cwd,
        provider=context.citation_provider,
        evidence_mode=context.citation_evidence_mode,
    )
    refreshed = _refresh_citation_integrity_for_current_manuscript(context.cwd, quality_mode=context.quality_mode)
    attempted: dict[str, Any] = {
        "code": code,
        "handler": "refresh_citation_quality",
        "citation_support_review": str(review_path),
        "citation_integrity": refreshed,
    }
    if bibtex_rebuild is not None:
        attempted["bibtex_rebuild"] = bibtex_rebuild
    execution["actions_attempted"].append(attempted)
    return True


def handle_citation_integrity_refresh(
    code: str,
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
    state: _QaLoopActionDispatchState,
) -> bool:
    refreshed = _refresh_citation_integrity_for_current_manuscript(context.cwd, quality_mode=context.quality_mode)
    execution["actions_attempted"].append(
        {"code": code, "handler": "refresh_citation_integrity", "artifacts": refreshed}
    )
    return True
