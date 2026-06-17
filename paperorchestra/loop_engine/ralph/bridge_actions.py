from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.ralph.state import SUPPORTED_HANDLER_CODES


def _executable_actions(plan: dict[str, Any]) -> list[dict[str, Any]]:
    actions = plan.get("repair_actions") if isinstance(plan, dict) else []
    return [
        action
        for action in actions
        if isinstance(action, dict)
        and action.get("automation") in {"automatic", "semi_auto"}
        and str(action.get("code")) in SUPPORTED_HANDLER_CODES
    ]

def _unsupported_executable_actions(plan: dict[str, Any]) -> list[dict[str, Any]]:
    actions = plan.get("repair_actions") if isinstance(plan, dict) else []
    return [
        action
        for action in actions
        if isinstance(action, dict)
        and action.get("automation") in {"automatic", "semi_auto"}
        and str(action.get("code")) not in SUPPORTED_HANDLER_CODES
    ]
