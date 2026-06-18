from __future__ import annotations

from typing import Any

from paperorchestra.feedback.operator_issue_constants import ACTIONABLE_FAILURE_OWNER_CATEGORIES


def _owner_category_for_issue(issue: dict[str, Any]) -> str:
    text = " ".join(
        str(issue.get(key) or "")
        for key in ("target_section", "rationale", "suggested_action", "authority_class")
    ).lower()
    if any(token in text for token in ("experiment", "benchmark", "evaluation", "result")):
        return "experiment"
    if any(token in text for token in ("proof", "theorem", "security", "bound")):
        return "proof"
    if any(token in text for token in ("citation", "bibliography", "reference", "bibtex")):
        return "bibliography"
    if any(token in text for token in ("compile", "validation", "implementation", "execution")):
        return "implementation"
    return "author"


def _validated_owner_category(issue: dict[str, Any]) -> str:
    owner_category = str(issue.get("owner_category") or _owner_category_for_issue(issue))
    if owner_category not in ACTIONABLE_FAILURE_OWNER_CATEGORIES:
        from paperorchestra.core.errors import ContractError

        raise ContractError(f"invalid owner_category for operator issue: {owner_category}")
    return owner_category
