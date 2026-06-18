from __future__ import annotations

from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.engine.schema_common import _closed_object_schema

_PLOT_MANIFEST_ITEM_SCHEMA = _closed_object_schema(
    {
        "figure_id": {"type": "string"},
        "title": {"type": "string"},
        "plot_type": {"type": "string"},
        "data_source": {"type": "string"},
        "objective": {"type": "string"},
        "aspect_ratio": {"type": "string"},
        "rendering_brief": {"type": "string"},
        "caption": {"type": "string"},
        "source_fidelity_notes": {"type": "string"},
    }
)

PLOT_SCHEMA = {
    **_closed_object_schema(
        {
            "figures": {"type": "array", "items": _PLOT_MANIFEST_ITEM_SCHEMA},
        }
    )
}


def validate_plot_manifest(data: dict[str, Any]) -> None:
    if "figures" not in data or not isinstance(data["figures"], list):
        raise ContractError("Plot manifest must contain a figures list.")
    for figure in data["figures"]:
        for key in [
            "figure_id",
            "title",
            "plot_type",
            "data_source",
            "objective",
            "aspect_ratio",
            "rendering_brief",
            "caption",
            "source_fidelity_notes",
        ]:
            if key not in figure:
                raise ContractError(f"Plot manifest figure missing key: {key}")
