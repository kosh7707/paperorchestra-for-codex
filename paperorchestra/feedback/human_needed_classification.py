from __future__ import annotations

from typing import Any

from paperorchestra.feedback import human_needed_records as _records


def _classify_action(action: dict[str, Any] | None, *, candidate_role: str | None = None) -> str:
    if candidate_role:
        return "candidate_approval"
    text = _action_text(action)
    if _has_any(text, ("citation", "reference", "bibliography", "claim")):
        return "citation_author_judgment"
    if _has_any(text, ("figure", "plot", "caption", "asset")):
        return "figure_grounding_decision"
    if _has_any(text, ("environment", "dependency", "compile", "sandbox")):
        return "environment_dependency"
    if "reviewer" in text or "independent" in text:
        return "reviewer_independence"
    if _has_any(text, ("no_progress", "budget", "retry", "stuck")):
        return "no_progress_escalation"
    if _records._action_id(action) or (action or {}).get("code"):
        return "general_operator_feedback"
    return "unsupported_handler"


def _action_text(action: dict[str, Any] | None) -> str:
    return " ".join(
        str((action or {}).get(key) or "")
        for key in ("id", "action_id", "code", "target", "reason", "suggested_action")
    ).lower()


def _has_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)
