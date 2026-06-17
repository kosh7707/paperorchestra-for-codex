from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from paperorchestra.manuscript.sections import (
    _line_number,
    _section_for_index,
    _section_records,
    _substantive_text,
)

from paperorchestra.manuscript.figure_matching import (
    _body_figure_has_nontechnical_asset,
    _caption_has_process_or_placeholder_text,
    _caption_manifest_relation,
    _high_signal_tokens,
    _included_asset_names,
    _match_plot_manifest,
    _normalize_figure_key,
    _plot_asset_candidates,
    _plot_manifest_candidates,
    _asset_is_reviewable,
    _figure_keys,
    _NONTECHNICAL_VISUAL_STRONG_RE,
    _NONTECHNICAL_VISUAL_CONTEXT_RE,
    _DECORATIVE_VISUAL_RE,
    _PROCESS_CAPTION_RE,
    _UNRELATED_CAPTION_CUE_RE,
)
from paperorchestra.manuscript.figure_patterns import (
    CAPTION_RE,
    DECORATIVE_VISUAL_RE,
    FIGURE_ENV_RE,
    INCLUDE_GRAPHICS_RE,
    LABEL_RE,
    NONTECHNICAL_VISUAL_CONTEXT_RE,
    NONTECHNICAL_VISUAL_STRONG_RE,
    PROCESS_CAPTION_RE,
    REF_RE,
    UNRELATED_CAPTION_CUE_RE,
)

__all__ = [
    "CAPTION_RE",
    "FIGURE_ENV_RE",
    "INCLUDE_GRAPHICS_RE",
    "LABEL_RE",
    "REF_RE",
    "NONTECHNICAL_VISUAL_STRONG_RE",
    "NONTECHNICAL_VISUAL_CONTEXT_RE",
    "DECORATIVE_VISUAL_RE",
    "PROCESS_CAPTION_RE",
    "UNRELATED_CAPTION_CUE_RE",
    "FigurePlacementWarning",
    "build_figure_placement_review",
    "_normalize_figure_key",
    "_high_signal_tokens",
    "_plot_asset_candidates",
    "_plot_manifest_candidates",
    "_asset_is_reviewable",
    "_figure_keys",
    "_match_plot_manifest",
    "_caption_manifest_relation",
    "_included_asset_names",
    "_body_figure_has_nontechnical_asset",
    "_caption_has_process_or_placeholder_text",
]


@dataclass(frozen=True)
class FigurePlacementWarning:
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _source_figure_labels(source_latex: str | None) -> set[str]:
    if not source_latex:
        return set()
    labels: set[str] = set()
    for match in FIGURE_ENV_RE.finditer(source_latex):
        label_match = LABEL_RE.search(match.group(3))
        if label_match:
            labels.add(label_match.group(1))
    return labels


def _figure_source_origin(block: str, label: str | None, source_labels: set[str], *, prefix: str = "") -> str:
    if "PaperOrchestra:auto-repaired" in block or "PaperOrchestra:auto-repaired" in prefix:
        return "auto_repaired"
    if label and label in source_labels:
        return "source_preserved"
    return "model_written"


def _compact_context(text: str, *, start: int, end: int, limit: int = 500) -> str:
    left = max(0, start - limit // 2)
    right = min(len(text), end + limit // 2)
    snippet = text[left:right]
    snippet = re.sub(r"\s+", " ", snippet).strip()
    return snippet[:limit]


def _figure_ref_labels(match: re.Match[str]) -> set[str]:
    return {part.strip() for part in match.group(1).split(",") if part.strip()}


def _figure_warning(
    code: str,
    *,
    label: str | None,
    detail: str,
) -> FigurePlacementWarning:
    subject = label or "<unlabeled>"
    return FigurePlacementWarning(code=code, message=f"{subject}: {detail}")


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
    source_labels = _source_figure_labels(source_latex)
    conclusion_start = next((section["start"] for section in sections if section["normalized_title"] == "conclusion"), None)
    bibliography_start = latex.find(r"\bibliographystyle")
    if bibliography_start == -1:
        bibliography_start = latex.find(r"\bibliography")
    figures: list[dict[str, Any]] = []
    warnings: list[FigurePlacementWarning] = []
    failures: list[FigurePlacementWarning] = []
    tail_figures: list[int] = []

    for idx, match in enumerate(FIGURE_ENV_RE.finditer(latex), start=1):
        env = match.group(1)
        placement = match.group(2) or ""
        block = match.group(0)
        body = match.group(3)
        label_match = LABEL_RE.search(body)
        label = label_match.group(1) if label_match else None
        caption_match = CAPTION_RE.search(body)
        caption = caption_match.group(1).strip() if caption_match else ""
        start = match.start()
        end = match.end()
        start_line = _line_number(latex, start)
        end_line = _line_number(latex, end)
        section = _section_for_index(latex, start)
        section_title = section["title"] if section else ""
        refs = []
        if label:
            refs = [m for m in REF_RE.finditer(latex) if label in _figure_ref_labels(m) and not (start <= m.start() < end)]
        first_ref = refs[0] if refs else None
        first_ref_line = _line_number(latex, first_ref.start()) if first_ref else None
        first_ref_distance_lines = start_line - first_ref_line if first_ref_line is not None else None
        nearby_reference_context = (
            _compact_context(latex, start=first_ref.start(), end=first_ref.end()) if first_ref is not None else ""
        )
        included_assets = _included_asset_names(body)
        plot_match = _match_plot_manifest(
            label=label,
            caption=caption,
            included_assets=included_assets,
            plot_manifest=plot_manifest,
            plot_assets_index=plot_assets_index,
        )
        caption_relation = _caption_manifest_relation(caption, plot_match)
        figure_warnings: list[FigurePlacementWarning] = []
        figure_failures: list[FigurePlacementWarning] = []

        if conclusion_start is not None and start >= conclusion_start:
            figure_warnings.append(
                _figure_warning("after_conclusion", label=label, detail="Figure appears in or after the Conclusion section.")
            )
        if bibliography_start != -1 and start >= bibliography_start:
            figure_warnings.append(
                _figure_warning("tail_clump", label=label, detail="Figure appears after the bibliography hook area.")
            )
        elif start_line / total_lines >= tail_ratio_threshold:
            tail_figures.append(idx - 1)
        if first_ref_distance_lines is not None and first_ref_distance_lines > far_reference_line_threshold:
            figure_warnings.append(
                _figure_warning(
                    "far_from_first_reference",
                    label=label,
                    detail=f"Figure is {first_ref_distance_lines} lines after its first reference.",
                )
            )
        if not placement.strip():
            figure_warnings.append(
                _figure_warning("placement_hint_missing", label=label, detail="Figure environment has no placement specifier.")
            )
        if label and not refs:
            figure_warnings.append(
                _figure_warning("figure_unreferenced", label=label, detail="Figure has a label but no textual reference.")
            )
        if label and (not refs or (plot_match and plot_match.get("status") == "matched" and len(_substantive_text(nearby_reference_context)) < 40)):
            context_warning = _figure_warning(
                "figure_reference_context_missing",
                label=label,
                detail="Figure lacks a nearby substantive textual reference explaining what claim or result it supports.",
            )
            if plot_match and plot_match.get("status") == "matched" and caption_relation in {"mismatch", "uncertain"}:
                figure_failures.append(context_warning)
            else:
                figure_warnings.append(context_warning)
        if _body_figure_has_nontechnical_asset(body, caption):
            figure_failures.append(
                _figure_warning(
                    "nontechnical_visual_asset_in_body",
                    label=label,
                    detail="Figure appears to use an author/portrait/decorative asset in the manuscript body.",
                )
            )
        if _caption_has_process_or_placeholder_text(caption):
            figure_failures.append(
                _figure_warning(
                    "figure_caption_process_or_placeholder",
                    label=label,
                    detail="Caption contains process, placeholder, or non-evidence wording rather than scholarly figure content.",
                )
            )
        if plot_match and plot_match.get("status") == "ambiguous":
            figure_warnings.append(
                _figure_warning(
                    "figure_plot_manifest_match_ambiguous",
                    label=label,
                    detail="Figure could match multiple plot manifest entries; semantic caption review is conservative.",
                )
            )
        elif caption_relation == "mismatch":
            figure_failures.append(
                _figure_warning(
                    "figure_caption_plot_purpose_mismatch",
                    label=label,
                    detail="Caption appears unrelated to the matched plot manifest purpose or title.",
                )
            )
        elif caption_relation == "uncertain":
            figure_warnings.append(
                _figure_warning(
                    "figure_caption_plot_purpose_uncertain",
                    label=label,
                    detail="Caption has no high-signal token overlap with the matched plot manifest purpose/title; verify manually.",
                )
            )
        include_line = next((line for line in body.splitlines() if "\\includegraphics" in line or "\\input{" in line), "")
        if env == "figure*" and ("\\columnwidth" in include_line or "\\linewidth" in include_line):
            figure_warnings.append(
                _figure_warning(
                    "wide_figure_mismatch",
                    label=label,
                    detail="figure* uses a narrow-width include that looks single-column.",
                )
            )
        if env == "figure" and "\\textwidth" in include_line:
            figure_warnings.append(
                _figure_warning(
                    "wide_figure_mismatch",
                    label=label,
                    detail="Single-column figure uses textwidth and may need figure*.",
                )
            )

        warnings.extend(figure_warnings)
        failures.extend(figure_failures)
        figures.append(
            {
                "label": label or f"unnamed_{idx}",
                "caption": caption,
                "section_title": section_title,
                "figure_line": start_line,
                "figure_end_line": end_line,
                "figure_page": None,
                "first_reference_line": first_ref_line,
                "first_reference_page": None,
                "reference_distance_lines": first_ref_distance_lines,
                "reference_distance_pages": None,
                "placement_environment": env,
                "placement_specifier": placement,
                "included_assets": included_assets,
                "nearby_reference_context": nearby_reference_context,
                "plot_manifest_match": plot_match,
                "source_origin": _figure_source_origin(
                    block,
                    label,
                    source_labels,
                    prefix=latex[max(0, start - 120) : start],
                ),
                "failing_codes": [failure.code for failure in figure_failures],
                "warning_codes": [warning.code for warning in figure_warnings],
            }
        )

    if len(tail_figures) > 1:
        for index in tail_figures:
            warning = _figure_warning(
                "tail_clump",
                label=figures[index]["label"],
                detail="Figure is clustered in the tail of the manuscript.",
            )
            warnings.append(warning)
            figures[index]["warning_codes"].append("tail_clump")

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
            "warning_codes": sorted({warning.code for warning in warnings}),
            "failing_codes": failing_codes,
        },
    }
