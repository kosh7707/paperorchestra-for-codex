from __future__ import annotations

from typing import Any

from paperorchestra.engine.planning_stages import plan_narrative_and_claims as _plan_narrative_and_claims
from paperorchestra.engine.review_stages import (
    record_current_validation_report as _record_current_validation_report,
    write_figure_placement_review as _write_figure_placement_review,
)
from paperorchestra.reviews.citation_model_writer import write_citation_support_review as _write_citation_support_review
from paperorchestra.loop_engine.ralph.action_dispatch_dependencies import _handler_dependency
from paperorchestra.loop_engine.ralph.action_dispatch_types import QaLoopActionDispatchContext, _QaLoopActionDispatchState
from paperorchestra.loop_engine.ralph.artifacts import (
    _refresh_citation_integrity_for_current_manuscript as _refresh_citation_integrity_for_current_manuscript_real,
    _try_rebuild_bib_for_citation_quality as _try_rebuild_bib_for_citation_quality_real,
)


def _handle_narrative_plan(
    code: str,
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
    state: _QaLoopActionDispatchState,
) -> bool:
    paths = _handler_dependency("plan_narrative_and_claims", _plan_narrative_and_claims)(
        context.cwd,
        provider=None,
        runtime_mode=context.runtime_mode,
    )
    execution["actions_attempted"].append(
        {"code": code, "handler": "plan_narrative", "paths": {key: str(path) for key, path in paths.items()}}
    )
    return True


def _handle_validation_refresh(
    code: str,
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
    state: _QaLoopActionDispatchState,
) -> bool:
    validation_path, validation_payload = _handler_dependency(
        "record_current_validation_report",
        _record_current_validation_report,
    )(context.cwd, name="validation.qa-loop-step.precondition.json")
    execution["actions_attempted"].append(
        {"code": code, "handler": "validate_current", "path": str(validation_path), "ok": validation_payload.get("ok")}
    )
    return True


def _handle_figure_placement_review(
    code: str,
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
    state: _QaLoopActionDispatchState,
) -> bool:
    figure_path, figure_payload = _handler_dependency(
        "write_figure_placement_review",
        _write_figure_placement_review,
    )(context.cwd)
    warning_count = (
        (figure_payload.get("summary") or {}).get("warning_count")
        if isinstance(figure_payload, dict)
        else None
    )
    execution["actions_attempted"].append(
        {"code": code, "handler": "review_figure_placement", "path": str(figure_path), "warning_count": warning_count}
    )
    return True


def _handle_citation_support_review(
    code: str,
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
    state: _QaLoopActionDispatchState,
) -> bool:
    review_path = _handler_dependency("write_citation_support_review", _write_citation_support_review)(
        context.cwd,
        provider=context.citation_provider,
        evidence_mode=context.citation_evidence_mode,
    )
    execution["actions_attempted"].append({"code": code, "handler": "critique_citations", "path": str(review_path)})
    return True


def _handle_citation_quality_refresh(
    code: str,
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
    state: _QaLoopActionDispatchState,
) -> bool:
    bibtex_rebuild = (
        _handler_dependency("_try_rebuild_bib_for_citation_quality", _try_rebuild_bib_for_citation_quality_real)(context.cwd)
        if code == "critical_weak_reference_identity"
        else None
    )
    review_path = _handler_dependency("write_citation_support_review", _write_citation_support_review)(
        context.cwd,
        provider=context.citation_provider,
        evidence_mode=context.citation_evidence_mode,
    )
    refreshed = _handler_dependency(
        "_refresh_citation_integrity_for_current_manuscript",
        _refresh_citation_integrity_for_current_manuscript_real,
    )(context.cwd, quality_mode=context.quality_mode)
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


def _handle_citation_integrity_refresh(
    code: str,
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
    state: _QaLoopActionDispatchState,
) -> bool:
    refreshed = _handler_dependency(
        "_refresh_citation_integrity_for_current_manuscript",
        _refresh_citation_integrity_for_current_manuscript_real,
    )(context.cwd, quality_mode=context.quality_mode)
    execution["actions_attempted"].append(
        {"code": code, "handler": "refresh_citation_integrity", "artifacts": refreshed}
    )
    return True
