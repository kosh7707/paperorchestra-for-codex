from __future__ import annotations

import re
from typing import Any

from paperorchestra.manuscript.figure_matching_keys import _match_plot_manifest
from paperorchestra.manuscript.figure_matching_semantics import _caption_manifest_relation, _included_asset_names
from paperorchestra.manuscript.figure_patterns import CAPTION_RE, LABEL_RE
from paperorchestra.manuscript.figure_review_helpers import compact_context, figure_references, figure_source_origin
from paperorchestra.manuscript.figure_review_types import FigureContext
from paperorchestra.manuscript.sections import _line_number, _section_for_index


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


def _first_capture(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(1) if match else None


def _figure_section_title(latex: str, start: int) -> str:
    section = _section_for_index(latex, start)
    return section["title"] if section else ""


def _reference_context(latex: str, first_ref: re.Match[str] | None) -> str:
    if not first_ref:
        return ""
    return compact_context(latex, start=first_ref.start(), end=first_ref.end())
