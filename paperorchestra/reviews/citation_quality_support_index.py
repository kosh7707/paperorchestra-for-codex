from __future__ import annotations

from typing import Any


def _support_by_key(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        for key in item.get("citation_keys") or []:
            normalized = str(key).strip()
            if normalized:
                result.setdefault(normalized, []).append(item)
    return result


def _worst_support_status(items: list[dict[str, Any]]) -> str:
    if not items:
        return "unknown"
    order = ["contradicted", "unsupported", "metadata_only", "insufficient_evidence", "unknown", "supported"]
    statuses = {str(item.get("support_status") or "unknown").strip().lower() or "unknown" for item in items}
    for status in order:
        if status in statuses:
            return status
    return sorted(statuses)[0]
