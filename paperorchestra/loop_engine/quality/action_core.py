from __future__ import annotations

from typing import Any

from paperorchestra.manuscript.contract_refs import contract_context_for_text


def _action(
    *,
    action_id: str,
    code: str,
    source: str | None,
    reason: str,
    automation: str,
    target: str | None = None,
    suggested_commands: list[str] | None = None,
    ralph_instruction: str | None = None,
    why_not_automatic: str | None = None,
    approval_required_from: str | None = None,
    preconditions: list[str] | None = None,
) -> dict[str, Any]:
    contract_context = contract_context_for_text(
        code,
        target,
        reason,
        ralph_instruction,
        why_not_automatic,
        approval_required_from,
        automation=automation,
    )
    payload = {
        "id": action_id,
        "code": code,
        "source": source,
        "target": target,
        "automation": automation,
        "reason": reason,
        **contract_context,
        "suggested_commands": list(dict.fromkeys(suggested_commands or [])),
        "ralph_instruction": ralph_instruction or reason,
        "preconditions": preconditions or ["tier_1_structural must remain pass"],
    }
    if why_not_automatic:
        payload["why_not_automatic"] = why_not_automatic
    if approval_required_from:
        payload["approval_required_from"] = approval_required_from
    return payload
