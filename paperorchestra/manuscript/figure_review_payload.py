from __future__ import annotations

from typing import Any

from paperorchestra.manuscript.figure_review_types import FigureContext, FigurePlacementWarning


def _figure_payload(
    context: FigureContext,
    *,
    warnings: list[FigurePlacementWarning],
    failures: list[FigurePlacementWarning],
) -> dict[str, Any]:
    return {
        "label": context.payload_label,
        "caption": context.caption,
        "section_title": context.section_title,
        "figure_line": context.start_line,
        "figure_end_line": context.end_line,
        "figure_page": None,
        "first_reference_line": context.first_ref_line,
        "first_reference_page": None,
        "reference_distance_lines": context.first_ref_distance_lines,
        "reference_distance_pages": None,
        "placement_environment": context.env,
        "placement_specifier": context.placement,
        "included_assets": context.included_assets,
        "nearby_reference_context": context.nearby_reference_context,
        "plot_manifest_match": context.plot_match,
        "source_origin": context.source_origin,
        "failing_codes": [failure.code for failure in failures],
        "warning_codes": [warning.code for warning in warnings],
    }


def build_review_payload(
    *,
    figures: list[dict[str, Any]],
    warnings: list[FigurePlacementWarning],
    failures: list[FigurePlacementWarning],
    manuscript_path: str | None,
    pdf_path: str | None,
) -> dict[str, Any]:
    warning_codes = sorted({warning.code for warning in warnings})
    failing_codes = sorted({failure.code for failure in failures})
    return {
        "schema_version": "figure-placement-review/1",
        "status": "fail" if failing_codes else "warn" if warning_codes else "pass",
        "failing_codes": failing_codes,
        "warning_codes": warning_codes,
        "manuscript_path": manuscript_path,
        "pdf_path": pdf_path,
        "generated_at": None,
        "figures": figures,
        "warnings": [warning.to_dict() for warning in warnings],
        "failures": [failure.to_dict() for failure in failures],
        "summary": {
            "figure_count": len(figures),
            "warning_count": len(warnings),
            "warning_codes": warning_codes,
            "failing_codes": failing_codes,
        },
    }
