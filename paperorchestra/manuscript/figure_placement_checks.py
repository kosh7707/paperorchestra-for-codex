from __future__ import annotations

from typing import Any

from paperorchestra.manuscript.figure_review_helpers import figure_warning
from paperorchestra.manuscript.figure_review_types import FigurePlacementWarning, PlacementLocationContext


def placement_width_warnings(
    *,
    env: str,
    include_line: str,
    label: str | None,
) -> list[FigurePlacementWarning]:
    warnings: list[FigurePlacementWarning] = []
    if env == "figure*" and ("\\columnwidth" in include_line or "\\linewidth" in include_line):
        warnings.append(
            figure_warning(
                "wide_figure_mismatch",
                label=label,
                detail="figure* uses a narrow-width include that looks single-column.",
            )
        )
    if env == "figure" and "\\textwidth" in include_line:
        warnings.append(
            figure_warning(
                "wide_figure_mismatch",
                label=label,
                detail="Single-column figure uses textwidth and may need figure*.",
            )
        )
    return warnings


def after_conclusion_warning(ctx: PlacementLocationContext) -> FigurePlacementWarning | None:
    if ctx.conclusion_start is None or ctx.start < ctx.conclusion_start:
        return None
    return figure_warning(
        "after_conclusion",
        label=ctx.label,
        detail="Figure appears in or after the Conclusion section.",
    )


def bibliography_tail_warning(ctx: PlacementLocationContext) -> FigurePlacementWarning | None:
    if ctx.bibliography_start == -1 or ctx.start < ctx.bibliography_start:
        return None
    return figure_warning(
        "tail_clump",
        label=ctx.label,
        detail="Figure appears after the bibliography hook area.",
    )


def is_tail_candidate(ctx: PlacementLocationContext) -> bool:
    if ctx.bibliography_start != -1 and ctx.start >= ctx.bibliography_start:
        return False
    return ctx.start_line / ctx.total_lines >= ctx.tail_ratio_threshold


def far_reference_warning(ctx: PlacementLocationContext) -> FigurePlacementWarning | None:
    distance = ctx.first_ref_distance_lines
    if distance is None or distance <= ctx.far_reference_line_threshold:
        return None
    return figure_warning(
        "far_from_first_reference",
        label=ctx.label,
        detail=f"Figure is {distance} lines after its first reference.",
    )


def missing_placement_warning(ctx: PlacementLocationContext) -> FigurePlacementWarning | None:
    if ctx.placement.strip():
        return None
    return figure_warning(
        "placement_hint_missing",
        label=ctx.label,
        detail="Figure environment has no placement specifier.",
    )


def unreferenced_warning(ctx: PlacementLocationContext) -> FigurePlacementWarning | None:
    if not ctx.label or ctx.refs:
        return None
    return figure_warning(
        "figure_unreferenced",
        label=ctx.label,
        detail="Figure has a label but no textual reference.",
    )


def placement_location_warnings(ctx: PlacementLocationContext) -> tuple[list[FigurePlacementWarning], bool]:
    warnings = [
        warning
        for warning in (
            after_conclusion_warning(ctx),
            bibliography_tail_warning(ctx),
            far_reference_warning(ctx),
            missing_placement_warning(ctx),
            unreferenced_warning(ctx),
        )
        if warning is not None
    ]
    return warnings, is_tail_candidate(ctx)


def tail_clump_warnings(
    figures: list[dict[str, Any]],
    tail_figures: list[int],
) -> list[tuple[int, FigurePlacementWarning]]:
    if len(tail_figures) <= 1:
        return []
    return [
        (
            index,
            figure_warning(
                "tail_clump",
                label=figures[index]["label"],
                detail="Figure is clustered in the tail of the manuscript.",
            ),
        )
        for index in tail_figures
    ]
