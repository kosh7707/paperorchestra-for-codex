from __future__ import annotations

from typing import Any

from .policy import QA_LOOP_SUPPORTED_HANDLER_CODES


def _action_verdict(actions: list[dict[str, Any]]) -> tuple[str, str]:
    executable = [action for action in actions if action.get("automation") in {"automatic", "semi_auto"}]
    supported = [action for action in executable if str(action.get("code")) in QA_LOOP_SUPPORTED_HANDLER_CODES]
    if supported:
        return "continue", "automatic or semi-automatic repair actions remain within the iteration budget"
    if executable:
        return "human_needed", "repair actions exist, but no qa-loop-step handler is available for them yet"
    if any(action.get("automation") == "human_needed" for action in actions):
        return "human_needed", "only human/domain-judgment actions remain"
    return "human_needed", "quality evaluation is not ready but no safe automatic repair action remains"
