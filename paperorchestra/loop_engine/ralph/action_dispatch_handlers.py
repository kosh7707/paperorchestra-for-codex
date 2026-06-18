from __future__ import annotations

from typing import Any, Callable

from paperorchestra.core.session import load_session
from paperorchestra.engine.planning_stages import plan_narrative_and_claims
from paperorchestra.engine.refine_stages import refine_current_paper
from paperorchestra.engine.review_stages import (
    compile_current_paper,
    record_current_validation_report,
    review_current_paper,
    write_figure_placement_review,
)
from paperorchestra.manuscript.source_obligations import write_source_obligations
from paperorchestra.reviews.section_review import write_section_review
from paperorchestra.loop_engine.ralph.action_dispatch_codes import (
    CITATION_INTEGRITY_REFRESH_CODES,
    CITATION_QUALITY_REFRESH_CODES,
    CITATION_REPAIR_CODES,
    CITATION_SUPPORT_REVIEW_CODES,
    COMPILE_CODES,
    FIGURE_PLACEMENT_REVIEW_CODES,
    NARRATIVE_PLAN_CODES,
    REFINE_CODES,
    REVIEW_REFRESH_CODES,
    SECTION_REVIEW_CODES,
    SOURCE_OBLIGATION_CODES,
    VALIDATION_REFRESH_CODES,
)
from paperorchestra.loop_engine.ralph.action_dispatch_types import (
    QaLoopActionDispatchContext,
    _QaLoopActionDispatchState,
)
from paperorchestra.loop_engine.ralph.action_dispatch_citation_refresh import (
    handle_citation_integrity_refresh,
    handle_citation_quality_refresh,
    handle_citation_support_review,
)
from paperorchestra.loop_engine.ralph.action_dispatch_citation_repair import handle_citation_repair

ActionHandler = Callable[[str, dict[str, Any], QaLoopActionDispatchContext, _QaLoopActionDispatchState], bool]


def _handle_narrative_plan(
    code: str,
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
    state: _QaLoopActionDispatchState,
) -> bool:
    paths = plan_narrative_and_claims(
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
    validation_path, validation_payload = record_current_validation_report(
        context.cwd,
        name="validation.qa-loop-step.precondition.json",
    )
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
    figure_path, figure_payload = write_figure_placement_review(context.cwd)
    warning_count = (
        (figure_payload.get("summary") or {}).get("warning_count")
        if isinstance(figure_payload, dict)
        else None
    )
    execution["actions_attempted"].append(
        {"code": code, "handler": "review_figure_placement", "path": str(figure_path), "warning_count": warning_count}
    )
    return True


def _handle_review_refresh(
    code: str,
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
    state: _QaLoopActionDispatchState,
) -> bool:
    path = review_current_paper(
        context.cwd,
        context.provider,
        runtime_mode=context.runtime_mode,
    )
    execution["actions_attempted"].append({"code": code, "handler": "review", "path": str(path)})
    return True


def _handle_compile(
    code: str,
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
    state: _QaLoopActionDispatchState,
) -> bool:
    try:
        pdf_path = compile_current_paper(context.cwd)
    except Exception as exc:
        execution["actions_attempted"].append({"code": code, "handler": "compile", "ok": False, "error": str(exc)})
        return False
    execution["actions_attempted"].append({"code": code, "handler": "compile", "pdf": str(pdf_path), "ok": True})
    return True


def _handle_section_review(
    code: str,
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
    state: _QaLoopActionDispatchState,
) -> bool:
    path = write_section_review(context.cwd)
    execution["actions_attempted"].append({"code": code, "handler": "critique_sections", "path": str(path)})
    return True


def _handle_source_obligations(
    code: str,
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
    state: _QaLoopActionDispatchState,
) -> bool:
    path = write_source_obligations(context.cwd)
    execution["actions_attempted"].append({"code": code, "handler": "build_source_obligations", "path": str(path)})
    return True


def _handle_refine(
    code: str,
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
    state: _QaLoopActionDispatchState,
) -> bool:
    session = load_session(context.cwd)
    if not session.artifacts.latest_review_json:
        review_path = review_current_paper(
            context.cwd,
            context.provider,
            runtime_mode=context.runtime_mode,
        )
        execution["actions_attempted"].append(
            {"code": code, "handler": "review", "path": str(review_path), "reason": "required_before_refine"}
        )
    refine_result = refine_current_paper(
        context.cwd,
        context.provider,
        iterations=1,
        require_compile_for_accept=context.require_compile,
        runtime_mode=context.runtime_mode,
        claim_safe=context.quality_mode == "claim_safe",
    )
    section_path = write_section_review(context.cwd)
    execution["actions_attempted"].append(
        {"code": code, "handler": "refine", "result": refine_result, "section_review": str(section_path)}
    )
    return not any(not item.get("accepted", False) for item in refine_result)


ACTION_HANDLER_REGISTRY: tuple[tuple[frozenset[str], ActionHandler], ...] = (
    (frozenset(NARRATIVE_PLAN_CODES), _handle_narrative_plan),
    (frozenset(VALIDATION_REFRESH_CODES), _handle_validation_refresh),
    (frozenset(FIGURE_PLACEMENT_REVIEW_CODES), _handle_figure_placement_review),
    (frozenset(CITATION_SUPPORT_REVIEW_CODES), handle_citation_support_review),
    (frozenset(CITATION_QUALITY_REFRESH_CODES), handle_citation_quality_refresh),
    (frozenset(CITATION_INTEGRITY_REFRESH_CODES), handle_citation_integrity_refresh),
    (frozenset(REVIEW_REFRESH_CODES), _handle_review_refresh),
    (frozenset(COMPILE_CODES), _handle_compile),
    (frozenset(SECTION_REVIEW_CODES), _handle_section_review),
    (frozenset(SOURCE_OBLIGATION_CODES), _handle_source_obligations),
    (frozenset(REFINE_CODES), _handle_refine),
    (frozenset(CITATION_REPAIR_CODES), handle_citation_repair),
)


def handled_action_codes() -> set[str]:
    return {code for codes, _handler in ACTION_HANDLER_REGISTRY for code in codes}


def handler_for_code(code: str) -> ActionHandler | None:
    for codes, handler in ACTION_HANDLER_REGISTRY:
        if code in codes:
            return handler
    return None
