from __future__ import annotations

import re
from typing import Any

from paperorchestra.manuscript.figure_matching import (
    _body_figure_has_nontechnical_asset,
    _caption_has_process_or_placeholder_text,
)
from paperorchestra.manuscript.figure_review_helpers import figure_warning
from paperorchestra.manuscript.figure_review_types import FigurePlacementWarning
from paperorchestra.manuscript.sections import _substantive_text


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
