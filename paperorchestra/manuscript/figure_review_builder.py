from __future__ import annotations

from typing import Any

from paperorchestra.manuscript.figure_patterns import FIGURE_ENV_RE
from paperorchestra.manuscript.figure_review_helpers import bibliography_start_index, source_figure_labels
from paperorchestra.manuscript.figure_review_payload import build_review_payload
from paperorchestra.manuscript.figure_review_records import apply_tail_clump_warnings, build_figure_record
from paperorchestra.manuscript.figure_review_types import FigurePlacementWarning
from paperorchestra.manuscript.sections import _section_records


def _conclusion_start(sections: list[dict[str, Any]]) -> int | None:
    return next((section["start"] for section in sections if section["normalized_title"] == "conclusion"), None)


def build_figure_placement_review(
    latex: str,
    *,
    source_latex: str | None = None,
    manuscript_path: str | None = None,
    pdf_path: str | None = None,
    plot_manifest: dict[str, Any] | None = None,
    plot_assets_index: dict[str, Any] | None = None,
    tail_ratio_threshold: float = 0.85,
    far_reference_line_threshold: int = 80,
) -> dict[str, Any]:
    total_lines = max(1, latex.count("\n") + 1)
    sections = _section_records(latex)
    source_labels = source_figure_labels(source_latex)
    conclusion_start = _conclusion_start(sections)
    bibliography_start = bibliography_start_index(latex)
    figures: list[dict[str, Any]] = []
    warnings: list[FigurePlacementWarning] = []
    failures: list[FigurePlacementWarning] = []
    tail_figures: list[int] = []

    for idx, match in enumerate(FIGURE_ENV_RE.finditer(latex), start=1):
        figure, figure_warnings, figure_failures, is_tail_candidate = build_figure_record(
            latex=latex,
            match=match,
            idx=idx,
            total_lines=total_lines,
            source_labels=source_labels,
            conclusion_start=conclusion_start,
            bibliography_start=bibliography_start,
            plot_manifest=plot_manifest,
            plot_assets_index=plot_assets_index,
            tail_ratio_threshold=tail_ratio_threshold,
            far_reference_line_threshold=far_reference_line_threshold,
        )
        if is_tail_candidate:
            tail_figures.append(idx - 1)
        warnings.extend(figure_warnings)
        failures.extend(figure_failures)
        figures.append(figure)

    apply_tail_clump_warnings(figures, warnings, tail_figures)
    return build_review_payload(
        figures=figures,
        warnings=warnings,
        failures=failures,
        manuscript_path=manuscript_path,
        pdf_path=pdf_path,
    )
