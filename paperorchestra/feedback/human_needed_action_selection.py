from __future__ import annotations

from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.feedback import human_needed_records as _records


def _select_action(actions: list[dict[str, Any]], action_id: str | None, *, candidate_role: str | None) -> dict[str, Any] | None:
    if action_id:
        matches = [action for action in actions if _records._action_id(action) == action_id]
        if len(matches) != 1:
            raise ContractError(f"human_needed action_id not found or ambiguous: {action_id}")
        return matches[0]
    if len(actions) > 1 and not candidate_role:
        raise ContractError("multiple human_needed actions require --action-id")
    if len(actions) == 1:
        return actions[0]
    return None
