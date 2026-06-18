from __future__ import annotations

from typing import Any

from paperorchestra.manuscript.figure_review_types import FigurePlacementWarning


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
