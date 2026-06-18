from __future__ import annotations

from typing import Any


def figure_grounding_issue_figures(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _figure_grounding_issue_item(item)
        for item in payload.get("figures") or []
        if isinstance(item, dict) and (item.get("failing_codes") or item.get("warning_codes"))
    ]


def _figure_grounding_issue_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": str(item.get("label") or ""),
        "section_title": str(item.get("section_title") or ""),
        "failing_codes": [str(code) for code in item.get("failing_codes") or [] if str(code).strip()],
        "warning_codes": [str(code) for code in item.get("warning_codes") or [] if str(code).strip()],
        "included_assets": [str(asset) for asset in item.get("included_assets") or [] if str(asset).strip()],
        "nearby_reference_context": str(item.get("nearby_reference_context") or "")[:500],
        "plot_manifest_match": item.get("plot_manifest_match") if isinstance(item.get("plot_manifest_match"), dict) else None,
    }
