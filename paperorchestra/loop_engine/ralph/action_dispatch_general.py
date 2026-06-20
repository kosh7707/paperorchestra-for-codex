from __future__ import annotations

from typing import Any

from paperorchestra.core.session import load_session
from paperorchestra.engine.planning_stages import plan_narrative_and_claims
from paperorchestra.engine.refine_stages import refine_current_paper
from paperorchestra.engine.review_stages import (
    compile_current_paper,
    record_current_validation_report,
    review_current_paper,
    write_figure_placement_review,
    write_page_layout_review,
    write_visual_repair_candidate,
    write_visual_repair_brief,
)
from paperorchestra.loop_engine.ralph.action_dispatch_types import (
    QaLoopActionDispatchContext,
    _QaLoopActionDispatchState,
)
from paperorchestra.manuscript.source_obligation_eval import write_source_obligations
from paperorchestra.reviews.section_review import write_section_review


def handle_narrative_plan(
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


def handle_validation_refresh(
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


def handle_figure_placement_review(
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


def handle_page_layout_review(
    code: str,
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
    state: _QaLoopActionDispatchState,
) -> bool:
    page_path, page_payload = write_page_layout_review(context.cwd)
    execution["actions_attempted"].append(
        {
            "code": code,
            "handler": "review_page_layout",
            "path": str(page_path),
            "status": page_payload.get("status"),
            "warning_codes": page_payload.get("warning_codes", []),
            "failing_codes": page_payload.get("failing_codes", []),
        }
    )
    return True


def handle_visual_repair_brief(
    code: str,
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
    state: _QaLoopActionDispatchState,
) -> bool:
    brief_path, brief_payload = write_visual_repair_brief(context.cwd)
    execution["actions_attempted"].append(
        {
            "code": code,
            "handler": "write_visual_repair_brief",
            "path": str(brief_path),
            "action_count": brief_payload.get("action_count"),
            "status": brief_payload.get("status"),
        }
    )
    return True


def handle_visual_repair_candidate(
    code: str,
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
    state: _QaLoopActionDispatchState,
) -> bool:
    candidate_path, candidate_payload = write_visual_repair_candidate(context.cwd)
    execution["actions_attempted"].append(
        {
            "code": code,
            "handler": "write_visual_repair_candidate",
            "path": str(candidate_path),
            "candidate_count": candidate_payload.get("candidate_count"),
            "status": candidate_payload.get("status"),
        }
    )
    return True


def handle_review_refresh(
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


def handle_compile(
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


def handle_section_review(
    code: str,
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
    state: _QaLoopActionDispatchState,
) -> bool:
    path = write_section_review(context.cwd)
    execution["actions_attempted"].append({"code": code, "handler": "critique_sections", "path": str(path)})
    return True


def handle_source_obligations(
    code: str,
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
    state: _QaLoopActionDispatchState,
) -> bool:
    path = write_source_obligations(context.cwd)
    execution["actions_attempted"].append({"code": code, "handler": "build_source_obligations", "path": str(path)})
    return True


def handle_refine(
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
