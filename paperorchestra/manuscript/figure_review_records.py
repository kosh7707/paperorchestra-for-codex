from __future__ import annotations

import re
from typing import Any

from paperorchestra.manuscript.figure_matching import (
    _caption_manifest_relation,
    _included_asset_names,
    _match_plot_manifest,
)
from paperorchestra.manuscript.figure_patterns import CAPTION_RE, LABEL_RE
from paperorchestra.manuscript.figure_review_checks import (
    placement_location_warnings,
    placement_width_warnings,
    reference_context_warnings,
    semantic_grounding_warnings,
    tail_clump_warnings,
)
from paperorchestra.manuscript.figure_review_helpers import compact_context, figure_references, figure_source_origin
from paperorchestra.manuscript.figure_review_types import (
    FigureContext,
    FigurePlacementWarning,
    PlacementLocationContext,
)
from paperorchestra.manuscript.sections import _line_number, _section_for_index


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


def _extract_figure_context(
    *,
    latex: str,
    match: re.Match[str],
    idx: int,
    source_labels: set[str],
    plot_manifest: dict[str, Any] | None,
    plot_assets_index: dict[str, Any] | None,
) -> FigureContext:
    env = match.group(1)
    placement = match.group(2) or ""
    block = match.group(0)
    body = match.group(3)
    label = _first_capture(LABEL_RE, body)
    caption = (_first_capture(CAPTION_RE, body) or "").strip()
    start = match.start()
    end = match.end()
    start_line = _line_number(latex, start)
    end_line = _line_number(latex, end)
    refs = figure_references(latex, label=label, figure_start=start, figure_end=end)
    first_ref = refs[0] if refs else None
    first_ref_line = _line_number(latex, first_ref.start()) if first_ref else None
    first_ref_distance_lines = start_line - first_ref_line if first_ref_line is not None else None
    included_assets = _included_asset_names(body)
    plot_match = _match_plot_manifest(
        label=label,
        caption=caption,
        included_assets=included_assets,
        plot_manifest=plot_manifest,
        plot_assets_index=plot_assets_index,
    )
    return FigureContext(
        idx=idx,
        env=env,
        placement=placement,
        block=block,
        body=body,
        label=label,
        caption=caption,
        start=start,
        end=end,
        start_line=start_line,
        end_line=end_line,
        section_title=_figure_section_title(latex, start),
        refs=refs,
        first_ref=first_ref,
        first_ref_line=first_ref_line,
        first_ref_distance_lines=first_ref_distance_lines,
        nearby_reference_context=_reference_context(latex, first_ref),
        included_assets=included_assets,
        plot_match=plot_match,
        caption_relation=_caption_manifest_relation(caption, plot_match),
        source_origin=figure_source_origin(
            block,
            label,
            source_labels,
            prefix=latex[max(0, start - 120) : start],
        ),
    )


def _review_figure_context(
    context: FigureContext,
    *,
    total_lines: int,
    conclusion_start: int | None,
    bibliography_start: int,
    tail_ratio_threshold: float,
    far_reference_line_threshold: int,
) -> tuple[list[FigurePlacementWarning], list[FigurePlacementWarning], bool]:
    warnings, is_tail_candidate = placement_location_warnings(
        PlacementLocationContext(
            label=context.label,
            start=context.start,
            start_line=context.start_line,
            total_lines=total_lines,
            placement=context.placement,
            refs=context.refs,
            first_ref_distance_lines=context.first_ref_distance_lines,
            conclusion_start=conclusion_start,
            bibliography_start=bibliography_start,
            tail_ratio_threshold=tail_ratio_threshold,
            far_reference_line_threshold=far_reference_line_threshold,
        )
    )
    failures: list[FigurePlacementWarning] = []
    context_warnings, context_failures = reference_context_warnings(
        label=context.label,
        refs=context.refs,
        plot_match=context.plot_match,
        caption_relation=context.caption_relation,
        nearby_reference_context=context.nearby_reference_context,
    )
    semantic_warnings, semantic_failures = semantic_grounding_warnings(
        body=context.body,
        caption=context.caption,
        label=context.label,
        plot_match=context.plot_match,
        caption_relation=context.caption_relation,
    )
    warnings.extend(context_warnings)
    warnings.extend(semantic_warnings)
    warnings.extend(
        placement_width_warnings(
            env=context.env,
            include_line=_first_include_line(context.body),
            label=context.label,
        )
    )
    failures.extend(context_failures)
    failures.extend(semantic_failures)
    return warnings, failures, is_tail_candidate


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


def _first_capture(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(1) if match else None


def _first_include_line(body: str) -> str:
    return next((line for line in body.splitlines() if "\\includegraphics" in line or "\\input{" in line), "")


def _figure_section_title(latex: str, start: int) -> str:
    section = _section_for_index(latex, start)
    return section["title"] if section else ""


def _reference_context(latex: str, first_ref: re.Match[str] | None) -> str:
    if not first_ref:
        return ""
    return compact_context(latex, start=first_ref.start(), end=first_ref.end())
