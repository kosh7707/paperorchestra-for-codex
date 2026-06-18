from __future__ import annotations

from typing import Any

from paperorchestra.orchestra.figure_core import FigureSlot


def _slot_from_mapping(item: dict[str, Any], *, fallback_index: int, default_placeholder: bool) -> FigureSlot | None:
    identifier = item.get("figure_id") or item.get("id") or item.get("label") or item.get("filename") or f"figure_slot_{fallback_index}"
    purpose = item.get("purpose") or item.get("caption") or item.get("title") or item.get("description") or identifier
    placeholder = _slot_placeholder(item, default_placeholder=default_placeholder)
    if not isinstance(identifier, str) or not isinstance(purpose, str):
        return None
    return FigureSlot(slot_id=identifier, purpose=purpose, placeholder=placeholder)


def _slot_placeholder(item: dict[str, Any], *, default_placeholder: bool) -> bool:
    placeholder_value = item.get("placeholder")
    if placeholder_value is not None:
        return bool(placeholder_value)
    return bool(
        default_placeholder
        or item.get("asset_kind") == "generated_placeholder"
        or item.get("review_status") == "human_final_artwork_required"
    )
