from __future__ import annotations

from typing import Any, Iterable

from paperorchestra.orchestra.figure_core import FigureSlot
from paperorchestra.orchestra.figure_slot_mapping import _slot_from_mapping


def _slots_from_plot_assets(payload: Any) -> Iterable[FigureSlot | None]:
    if not isinstance(payload, dict):
        return []
    return (
        _slot_from_mapping(item, fallback_index=index, default_placeholder=True)
        for index, item in enumerate(payload.get("assets") or [], start=1)
        if isinstance(item, dict)
        and (item.get("asset_kind") == "generated_placeholder" or item.get("review_status") == "human_final_artwork_required")
    )


def _slots_from_manifest(payload: Any) -> Iterable[FigureSlot | None]:
    if not isinstance(payload, dict):
        return []
    return (
        _slot_from_mapping(item, fallback_index=index, default_placeholder=False)
        for index, item in enumerate(payload.get("figures") or [], start=1)
        if isinstance(item, dict)
    )


def _slots_from_captions(payload: Any) -> Iterable[FigureSlot | None]:
    if not isinstance(payload, dict):
        return []
    values = payload.get("captions") if isinstance(payload.get("captions"), list) else payload.get("figures")
    if values is not None:
        return (
            _slot_from_mapping(item, fallback_index=index, default_placeholder=True)
            for index, item in enumerate(values or [], start=1)
            if isinstance(item, dict)
        )
    return (
        FigureSlot(slot_id=identifier, purpose=caption, placeholder=True)
        for identifier, caption in payload.items()
        if isinstance(identifier, str) and isinstance(caption, str)
    )
