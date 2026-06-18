from __future__ import annotations

from typing import Any

from paperorchestra.core.boundary import is_material_packet_control_section_title, is_material_packet_section_title
from paperorchestra.manuscript.structure import _canonical_generated_section_title


def _filtered_outline_for_sections(outline: dict[str, Any], selected_sections: list[str]) -> dict[str, Any]:
    selected = {item.strip().lower() for item in selected_sections}
    filtered = dict(outline)
    section_plan = outline.get("section_plan", []) if isinstance(outline, dict) else []
    filtered["section_plan"] = [
        item
        for item in section_plan
        if isinstance(item, dict) and str(item.get("section_title") or "").strip().lower() in selected
    ]
    return filtered


def _expected_section_titles_from_outline(outline: dict[str, Any]) -> list[str]:
    titles: list[str] = []
    saw_material_packet_control_section = False
    ignored = {"abstract", "appendix", "cross-cutting citation coverage checklist"}
    for item in outline.get("section_plan", []):
        if not isinstance(item, dict):
            continue
        title = item.get("section_title")
        if not isinstance(title, str) or not title.strip():
            continue
        normalized = _canonical_generated_section_title(title)
        if is_material_packet_control_section_title(title):
            saw_material_packet_control_section = True
        if normalized in ignored or normalized.startswith("appendix") or is_material_packet_section_title(title) or "checklist" in normalized:
            continue
        titles.append(normalized if normalized in {"method", "experiments", "discussion"} else title.strip())
    if saw_material_packet_control_section and not any(title.strip().lower() == "discussion" for title in titles):
        titles.append("Discussion")
    return titles
