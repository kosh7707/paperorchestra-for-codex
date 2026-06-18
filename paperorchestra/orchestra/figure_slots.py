from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paperorchestra.orchestra.figure_core import FigureSlot


def _read_json_if_exists(path: str | Path | None) -> Any:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists():
        return None
    return json.loads(candidate.read_text(encoding="utf-8"))


def _slot_from_mapping(item: dict[str, Any], *, fallback_index: int, default_placeholder: bool) -> FigureSlot | None:
    identifier = item.get("figure_id") or item.get("id") or item.get("label") or item.get("filename") or f"figure_slot_{fallback_index}"
    purpose = item.get("purpose") or item.get("caption") or item.get("title") or item.get("description") or identifier
    placeholder_value = item.get("placeholder")
    if placeholder_value is None:
        placeholder = bool(
            default_placeholder
            or item.get("asset_kind") == "generated_placeholder"
            or item.get("review_status") == "human_final_artwork_required"
        )
    else:
        placeholder = bool(placeholder_value)
    if not isinstance(identifier, str) or not isinstance(purpose, str):
        return None
    return FigureSlot(slot_id=identifier, purpose=purpose, placeholder=placeholder)


def derive_figure_slots(
    *,
    plot_assets_path: str | Path | None = None,
    plot_manifest_path: str | Path | None = None,
    plot_captions_path: str | Path | None = None,
) -> list[FigureSlot]:
    slots: list[FigureSlot] = []
    seen: set[str] = set()

    def append(slot: FigureSlot | None) -> None:
        if slot is None or slot.slot_id in seen:
            return
        seen.add(slot.slot_id)
        slots.append(slot)

    assets_payload = _read_json_if_exists(plot_assets_path)
    if isinstance(assets_payload, dict):
        for index, item in enumerate(assets_payload.get("assets") or [], start=1):
            if not isinstance(item, dict):
                continue
            if item.get("asset_kind") == "generated_placeholder" or item.get("review_status") == "human_final_artwork_required":
                append(_slot_from_mapping(item, fallback_index=index, default_placeholder=True))

    manifest_payload = _read_json_if_exists(plot_manifest_path)
    if isinstance(manifest_payload, dict):
        for index, item in enumerate(manifest_payload.get("figures") or [], start=1):
            if isinstance(item, dict):
                append(_slot_from_mapping(item, fallback_index=index, default_placeholder=False))

    captions_payload = _read_json_if_exists(plot_captions_path)
    if isinstance(captions_payload, dict):
        values = captions_payload.get("captions") if isinstance(captions_payload.get("captions"), list) else captions_payload.get("figures")
        for index, item in enumerate(values or [], start=1):
            if isinstance(item, dict):
                append(_slot_from_mapping(item, fallback_index=index, default_placeholder=True))
        if values is None:
            for identifier, caption in captions_payload.items():
                if isinstance(identifier, str) and isinstance(caption, str):
                    append(FigureSlot(slot_id=identifier, purpose=caption, placeholder=True))

    return slots
