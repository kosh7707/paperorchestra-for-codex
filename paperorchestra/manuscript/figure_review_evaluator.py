from __future__ import annotations

from paperorchestra.manuscript.figure_placement_checks import (
    placement_location_warnings,
    placement_width_warnings,
)
from paperorchestra.manuscript.figure_semantic_checks import (
    reference_context_warnings,
    semantic_grounding_warnings,
)
from paperorchestra.manuscript.figure_review_types import FigureContext, FigurePlacementWarning, PlacementLocationContext


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


def _first_include_line(body: str) -> str:
    return next((line for line in body.splitlines() if "\\includegraphics" in line or "\\input{" in line), "")
