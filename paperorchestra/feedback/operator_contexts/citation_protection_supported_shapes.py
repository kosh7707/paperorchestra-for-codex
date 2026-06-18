from __future__ import annotations

from typing import Any

from paperorchestra.feedback.operator_contexts.text import _normalized_context_text

_ITEM_REQUIRED_ACTION = (
    "preserve this already-supported citation-bearing sentence unless an active issue explicitly targets it"
)
_CASE_REQUIRED_ACTION = (
    "preserve this already-supported citation-bearing anchor unless an active issue explicitly targets it"
)


def _supported_item_context(
    item: dict[str, Any],
    targets: dict[str, set[str]],
    *,
    ordinal: int,
) -> dict[str, Any] | None:
    status = str(item.get("support_status") or item.get("status") or "").strip()
    if status != "supported":
        return None
    sentence = _normalized_context_text(item.get("sentence"))
    keys = [str(key).strip() for key in item.get("citation_keys") or [] if str(key).strip()]
    entry_id = str(item.get("id") or "").strip()
    if not sentence or _is_excluded_target(targets, entry_id, sentence, keys):
        return None
    return {
        "id": entry_id or f"supported-item-{ordinal}",
        "citation_keys": keys,
        "sentence": sentence,
        "source_shape": "items",
        "required_action": _ITEM_REQUIRED_ACTION,
    }


def _supported_case_context(
    case: dict[str, Any],
    targets: dict[str, set[str]],
    *,
    ordinal: int,
) -> dict[str, Any] | None:
    verdict = str(case.get("verdict") or case.get("support_status") or case.get("status") or "").strip()
    if verdict not in {"pass", "supported"}:
        return None
    anchor = _normalized_context_text(case.get("anchor") or case.get("target"))
    keys = [str(case.get("key")).strip()] if str(case.get("key") or "").strip() else []
    entry_id = str(case.get("id") or "").strip()
    if not anchor or _is_excluded_target(targets, entry_id, anchor, keys):
        return None
    return {
        "id": entry_id or f"supported-case-{ordinal}",
        "citation_keys": keys,
        "anchor": anchor,
        "source_shape": "cases",
        "required_action": _CASE_REQUIRED_ACTION,
    }


def _protected_item_text(item: dict[str, Any]) -> str:
    return _normalized_context_text(item.get("sentence") or item.get("anchor"))


def _is_excluded_target(targets: dict[str, set[str]], entry_id: str, text: str, keys: list[str]) -> bool:
    if entry_id and entry_id in targets["ids"]:
        return True
    normalized = _normalized_context_text(text)
    if normalized and normalized in targets["texts"]:
        return True
    return bool(set(keys) & targets["key_exclusions"])
