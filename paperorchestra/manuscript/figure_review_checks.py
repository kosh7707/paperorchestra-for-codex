from __future__ import annotations

import re
from typing import Any

from paperorchestra.manuscript.figure_matching import (
    _body_figure_has_nontechnical_asset,
    _caption_has_process_or_placeholder_text,
)
from paperorchestra.manuscript.figure_review_helpers import figure_warning
from paperorchestra.manuscript.figure_review_types import FigurePlacementWarning, PlacementLocationContext
from paperorchestra.manuscript.sections import _substantive_text


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


def reference_context_warnings(
    *,
    label: str | None,
    refs: list[re.Match[str]],
    plot_match: dict[str, Any] | None,
    caption_relation: str,
    nearby_reference_context: str,
) -> tuple[list[FigurePlacementWarning], list[FigurePlacementWarning]]:
    warnings: list[FigurePlacementWarning] = []
    failures: list[FigurePlacementWarning] = []
    reference_context_missing = label and (
        not refs
        or (
            plot_match
            and plot_match.get("status") == "matched"
            and len(_substantive_text(nearby_reference_context)) < 40
        )
    )
    if not reference_context_missing:
        return warnings, failures
    context_warning = figure_warning(
        "figure_reference_context_missing",
        label=label,
        detail="Figure lacks a nearby substantive textual reference explaining what claim or result it supports.",
    )
    if plot_match and plot_match.get("status") == "matched" and caption_relation in {"mismatch", "uncertain"}:
        failures.append(context_warning)
    else:
        warnings.append(context_warning)
    return warnings, failures


def semantic_grounding_warnings(
    *,
    body: str,
    caption: str,
    label: str | None,
    plot_match: dict[str, Any] | None,
    caption_relation: str,
) -> tuple[list[FigurePlacementWarning], list[FigurePlacementWarning]]:
    warnings: list[FigurePlacementWarning] = []
    failures: list[FigurePlacementWarning] = []
    if _body_figure_has_nontechnical_asset(body, caption):
        failures.append(
            figure_warning(
                "nontechnical_visual_asset_in_body",
                label=label,
                detail="Figure appears to use an author/portrait/decorative asset in the manuscript body.",
            )
        )
    if _caption_has_process_or_placeholder_text(caption):
        failures.append(
            figure_warning(
                "figure_caption_process_or_placeholder",
                label=label,
                detail=(
                    "Caption contains process, placeholder, or non-evidence wording "
                    "rather than scholarly figure content."
                ),
            )
        )
    if plot_match and plot_match.get("status") == "ambiguous":
        warnings.append(
            figure_warning(
                "figure_plot_manifest_match_ambiguous",
                label=label,
                detail="Figure could match multiple plot manifest entries; semantic caption review is conservative.",
            )
        )
    elif caption_relation == "mismatch":
        failures.append(
            figure_warning(
                "figure_caption_plot_purpose_mismatch",
                label=label,
                detail="Caption appears unrelated to the matched plot manifest purpose or title.",
            )
        )
    elif caption_relation == "uncertain":
        warnings.append(
            figure_warning(
                "figure_caption_plot_purpose_uncertain",
                label=label,
                detail=(
                    "Caption has no high-signal token overlap with the matched plot manifest "
                    "purpose/title; verify manually."
                ),
            )
        )
    return warnings, failures
