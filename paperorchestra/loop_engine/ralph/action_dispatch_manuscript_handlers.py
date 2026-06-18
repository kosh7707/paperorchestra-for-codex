from __future__ import annotations

import sys
from typing import Any

from paperorchestra.core.session import load_session as _load_session
from paperorchestra.engine.refine_stages import refine_current_paper as _refine_current_paper
from paperorchestra.engine.review_stages import (
    compile_current_paper as _compile_current_paper,
    review_current_paper as _review_current_paper,
)
from paperorchestra.manuscript.source_obligations import write_source_obligations as _write_source_obligations
from paperorchestra.reviews.section_review import write_section_review as _write_section_review
from paperorchestra.loop_engine.ralph.action_dispatch_dependencies import _handler_dependency
from paperorchestra.loop_engine.ralph.action_dispatch_types import QaLoopActionDispatchContext, _QaLoopActionDispatchState


def _handle_review_refresh(
    code: str,
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
    state: _QaLoopActionDispatchState,
) -> bool:
    path = _handler_dependency("review_current_paper", _review_current_paper)(
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
        pdf_path = _handler_dependency("compile_current_paper", _compile_current_paper)(context.cwd)
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
    path = _handler_dependency("write_section_review", _write_section_review)(context.cwd)
    execution["actions_attempted"].append({"code": code, "handler": "critique_sections", "path": str(path)})
    return True


def _handle_source_obligations(
    code: str,
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
    state: _QaLoopActionDispatchState,
) -> bool:
    path = _handler_dependency("write_source_obligations", _write_source_obligations)(context.cwd)
    execution["actions_attempted"].append({"code": code, "handler": "build_source_obligations", "path": str(path)})
    return True


def _handle_refine(
    code: str,
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
    state: _QaLoopActionDispatchState,
) -> bool:
    session = _handler_dependency("load_session", _load_session)(context.cwd)
    if not session.artifacts.latest_review_json:
        review_path = _handler_dependency("review_current_paper", _review_current_paper)(
            context.cwd,
            context.provider,
            runtime_mode=context.runtime_mode,
        )
        execution["actions_attempted"].append(
            {"code": code, "handler": "review", "path": str(review_path), "reason": "required_before_refine"}
        )
    refine_result = _handler_dependency("refine_current_paper", _refine_current_paper)(
        context.cwd,
        context.provider,
        iterations=1,
        require_compile_for_accept=context.require_compile,
        runtime_mode=context.runtime_mode,
        claim_safe=context.quality_mode == "claim_safe",
    )
    section_path = _handler_dependency("write_section_review", _write_section_review)(context.cwd)
    execution["actions_attempted"].append(
        {"code": code, "handler": "refine", "result": refine_result, "section_review": str(section_path)}
    )
    return not any(not item.get("accepted", False) for item in refine_result)
