from __future__ import annotations

from pathlib import Path

from paperorchestra.orchestra.figure_core import FigureSlot
from paperorchestra.orchestra.figure_slot_io import _read_json_if_exists
from paperorchestra.orchestra.figure_slot_mapping import _slot_from_mapping
from paperorchestra.orchestra.figure_slot_sources import _slots_from_captions, _slots_from_manifest, _slots_from_plot_assets


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

    for slot in _slots_from_plot_assets(_read_json_if_exists(plot_assets_path)):
        append(slot)
    for slot in _slots_from_manifest(_read_json_if_exists(plot_manifest_path)):
        append(slot)
    for slot in _slots_from_captions(_read_json_if_exists(plot_captions_path)):
        append(slot)
    return slots


__all__ = ["_read_json_if_exists", "_slot_from_mapping", "derive_figure_slots"]
