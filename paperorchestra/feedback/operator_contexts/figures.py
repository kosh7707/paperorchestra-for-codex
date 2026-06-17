from __future__ import annotations

from typing import Any

from paperorchestra.feedback.operator_contexts.text import _truncate_context_text


def _figure_issue_context(payload: dict[str, Any] | None, *, limit: int = 12) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    result: list[dict[str, Any]] = []
    for item in payload.get("figures") or []:
        if not isinstance(item, dict):
            continue
        failing = [str(code) for code in item.get("failing_codes") or [] if str(code).strip()]
        warnings = [str(code) for code in item.get("warning_codes") or [] if str(code).strip()]
        if not failing and not warnings:
            continue
        result.append(
            {
                "issue_type": "figure_grounding",
                "label": str(item.get("label") or ""),
                "section_title": str(item.get("section_title") or ""),
                "failing_codes": failing,
                "warning_codes": warnings,
                "caption": _truncate_context_text(item.get("caption"), limit=500),
                "included_assets": [str(asset) for asset in item.get("included_assets") or [] if str(asset).strip()],
                "nearby_reference_context": _truncate_context_text(item.get("nearby_reference_context"), limit=500),
                "plot_manifest_match": item.get("plot_manifest_match")
                if isinstance(item.get("plot_manifest_match"), dict)
                else None,
                "suggested_fix": (
                    "Remove or quarantine nontechnical/decorative assets, replace placeholder or process captions "
                    "with scholarly figure content, and keep only figures that are referenced near the claims they support."
                ),
            }
        )
        if len(result) >= limit:
            break
    return result
