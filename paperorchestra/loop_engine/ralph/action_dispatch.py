from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.ralph.action_dispatch_handlers import handler_for_code
from paperorchestra.loop_engine.ralph.action_dispatch_types import (
    QaLoopActionDispatchContext as _QaLoopActionDispatchContext,
    QaLoopActionDispatchResult as _QaLoopActionDispatchResult,
    _QaLoopActionDispatchState,
)


def dispatch_qa_loop_actions(
    actions: list[dict[str, Any]],
    execution: dict[str, Any],
    context: _QaLoopActionDispatchContext,
) -> _QaLoopActionDispatchResult:
    state = _QaLoopActionDispatchState()
    for action in actions:
        code = str(action.get("code"))
        handler = handler_for_code(code)
        if handler is None:
            execution["actions_skipped"].append({"code": code, "reason": "no_handler"})
            continue
        if not handler(code, execution, context, state):
            break
    return _QaLoopActionDispatchResult(
        citation_candidate_applied=state.citation_candidate_applied,
        citation_candidate_path=state.citation_candidate_path,
    )
