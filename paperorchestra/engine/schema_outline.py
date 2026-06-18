from __future__ import annotations

from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.engine.schema_common import (
    VALID_ASPECT_RATIOS,
    VALID_PLOT_TYPES,
    _closed_object_schema,
    _string_list_schema,
)

_OUTLINE_PLOTTING_ITEM_SCHEMA = _closed_object_schema(
    {
        "figure_id": {"type": "string"},
        "title": {"type": "string"},
        "plot_type": {"type": "string"},
        "data_source": {"type": "string"},
        "objective": {"type": "string"},
        "aspect_ratio": {"type": "string"},
    }
)

_OUTLINE_INTRODUCTION_STRATEGY_SCHEMA = _closed_object_schema(
    {
        "hook_hypothesis": {"type": "string"},
        "problem_gap_hypothesis": {"type": "string"},
        "search_directions": _string_list_schema(),
    }
)

_OUTLINE_RELATED_SUBSECTION_SCHEMA = _closed_object_schema(
    {
        "subsection_title": {"type": "string"},
        "methodology_cluster": {"type": "string"},
        "sota_investigation_mission": {"type": "string"},
        "limitation_hypothesis": {"type": "string"},
        "limitation_search_queries": _string_list_schema(),
        "bridge_to_our_method": {"type": "string"},
    }
)

_OUTLINE_RELATED_WORK_STRATEGY_SCHEMA = _closed_object_schema(
    {
        "overview": {"type": "string"},
        "subsections": {"type": "array", "items": _OUTLINE_RELATED_SUBSECTION_SCHEMA},
    }
)

_OUTLINE_INTRO_RELATED_WORK_PLAN_SCHEMA = _closed_object_schema(
    {
        "introduction_strategy": _OUTLINE_INTRODUCTION_STRATEGY_SCHEMA,
        "related_work_strategy": _OUTLINE_RELATED_WORK_STRATEGY_SCHEMA,
    }
)

_OUTLINE_SECTION_SUBSECTION_SCHEMA = _closed_object_schema(
    {
        "subsection_title": {"type": "string"},
        "content_bullets": _string_list_schema(),
        "citation_hints": _string_list_schema(),
    }
)

_OUTLINE_SECTION_ITEM_SCHEMA = _closed_object_schema(
    {
        "section_title": {"type": "string"},
        "subsections": {"type": "array", "items": _OUTLINE_SECTION_SUBSECTION_SCHEMA},
    }
)

OUTLINE_SCHEMA = {
    **_closed_object_schema(
        {
            "plotting_plan": {"type": "array", "items": _OUTLINE_PLOTTING_ITEM_SCHEMA},
            "intro_related_work_plan": _OUTLINE_INTRO_RELATED_WORK_PLAN_SCHEMA,
            "section_plan": {"type": "array", "items": _OUTLINE_SECTION_ITEM_SCHEMA},
        }
    )
}


def validate_outline(data: dict[str, Any]) -> None:
    missing = {"plotting_plan", "intro_related_work_plan", "section_plan"} - set(data)
    if missing:
        raise ContractError(f"Outline missing required keys: {sorted(missing)}")
    if not isinstance(data["plotting_plan"], list):
        raise ContractError("plotting_plan must be a list.")
    for plot in data["plotting_plan"]:
        for key in ["figure_id", "title", "plot_type", "data_source", "objective", "aspect_ratio"]:
            if key not in plot:
                raise ContractError(f"plotting_plan item missing key: {key}")
        if plot["plot_type"] not in VALID_PLOT_TYPES:
            raise ContractError(f"Invalid plot_type: {plot['plot_type']}")
        if plot["aspect_ratio"] not in VALID_ASPECT_RATIOS:
            raise ContractError(f"Invalid aspect_ratio: {plot['aspect_ratio']}")


def _normalize_plot_type(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in VALID_PLOT_TYPES:
        return normalized
    if "diagram" in normalized:
        return "diagram"
    return "plot"


def _normalize_aspect_ratio(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in VALID_ASPECT_RATIOS:
        return normalized
    aliases = {
        "wide": "16:9",
        "landscape": "16:9",
        "standard": "4:3",
        "square": "1:1",
        "portrait": "3:4",
    }
    return aliases.get(normalized, "16:9")


def normalize_outline_payload(payload: dict[str, Any]) -> dict[str, Any]:
    plotting_plan = payload.get("plotting_plan")
    if isinstance(plotting_plan, list):
        for item in plotting_plan:
            if not isinstance(item, dict):
                continue
            plot_type = item.get("plot_type")
            if isinstance(plot_type, str) and plot_type not in VALID_PLOT_TYPES:
                original = plot_type
                item["plot_type"] = _normalize_plot_type(plot_type)
                objective = item.get("objective", "")
                if isinstance(objective, str) and original.lower() not in objective.lower():
                    item["objective"] = f"{objective} Original requested chart form: {original}."
            aspect_ratio = item.get("aspect_ratio")
            if isinstance(aspect_ratio, str) and aspect_ratio not in VALID_ASPECT_RATIOS:
                item["aspect_ratio"] = _normalize_aspect_ratio(aspect_ratio)
    return payload
