from __future__ import annotations

import re
from typing import Any

from paperorchestra.manuscript.figure_review_checks import tail_clump_warnings
from paperorchestra.manuscript.figure_review_context import (
    _extract_figure_context,
    _figure_section_title,
    _first_capture,
    _reference_context,
)
from paperorchestra.manuscript.figure_review_evaluator import _first_include_line, _review_figure_context
from paperorchestra.manuscript.figure_review_payload import _figure_payload
from paperorchestra.manuscript.figure_review_types import FigurePlacementWarning


def build_figure_record(
    *,
    latex: str,
    match: re.Match[str],
    idx: int,
    total_lines: int,
    source_labels: set[str],
    conclusion_start: int | None,
    bibliography_start: int,
    plot_manifest: dict[str, Any] | None,
    plot_assets_index: dict[str, Any] | None,
    tail_ratio_threshold: float,
    far_reference_line_threshold: int,
) -> tuple[dict[str, Any], list[FigurePlacementWarning], list[FigurePlacementWarning], bool]:
    context = _extract_figure_context(
        latex=latex,
        match=match,
        idx=idx,
        source_labels=source_labels,
        plot_manifest=plot_manifest,
        plot_assets_index=plot_assets_index,
    )
    warnings, failures, is_tail_candidate = _review_figure_context(
        context,
        total_lines=total_lines,
        conclusion_start=conclusion_start,
        bibliography_start=bibliography_start,
        tail_ratio_threshold=tail_ratio_threshold,
        far_reference_line_threshold=far_reference_line_threshold,
    )
    return _figure_payload(context, warnings=warnings, failures=failures), warnings, failures, is_tail_candidate


def apply_tail_clump_warnings(
    figures: list[dict[str, Any]],
    warnings: list[FigurePlacementWarning],
    tail_figures: list[int],
) -> None:
    for index, warning in tail_clump_warnings(figures, tail_figures):
        figures[index]["warning_codes"].append(warning.code)
        warnings.append(warning)


__all__ = [
    "_extract_figure_context",
    "_figure_payload",
    "_figure_section_title",
    "_first_capture",
    "_first_include_line",
    "_reference_context",
    "_review_figure_context",
    "apply_tail_clump_warnings",
    "build_figure_record",
]
