from __future__ import annotations

from typing import Any


def _as_strings(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(value).strip() for value in values if str(value).strip()]


def normalized_coverage_groups(claim: dict[str, Any]) -> list[list[str]]:
    groups = claim.get("coverage_groups")
    if isinstance(groups, list):
        normalized = [_normalized_group(group) for group in groups]
        normalized = [group for group in normalized if group]
        if normalized:
            return normalized
    terms = _as_strings(claim.get("coverage_terms"))
    return [[term] for term in terms]


def _normalized_group(group: Any) -> list[str]:
    return _as_strings(group) if isinstance(group, list) else _as_strings([group])
