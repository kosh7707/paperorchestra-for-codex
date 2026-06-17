from __future__ import annotations

from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import ExtractionError, extract_json, extract_latex
from paperorchestra.engine.latex_postprocess import (
    _ensure_bibliography_hook,
    _ensure_generated_plot_usage,
    _normalize_generated_plot_paths,
    _normalize_source_figure_paths,
    _stabilize_figure_float_placement,
)
from paperorchestra.manuscript.repair import (
    _ensure_discussion_section_for_claim_boundaries,
    _ensure_required_claim_scope_notes,
    _remove_material_packet_sections,
)
from paperorchestra.manuscript.validator import canonicalize_citation_keys


def parse_refinement_response(response: str, *, lane_notes: list[str]) -> tuple[dict[str, Any], str, list[str]]:
    try:
        worklog = extract_json(response)
    except ExtractionError:
        worklog = {
            "actions_taken": ["Refinement response did not include a machine-readable worklog block; accepted LaTeX-only fallback."],
            "addressed_weaknesses": [],
            "integrated_answers": [],
        }
        lane_notes = lane_notes + ["Refinement output omitted JSON worklog; synthesized fallback worklog from LaTeX-only response."]
    try:
        latex = extract_latex(response)
    except ExtractionError as exc:
        raise ContractError(f"Refinement output did not include extractable LaTeX: {exc}") from exc
    return worklog, latex, lane_notes


def normalize_refinement_latex(
    latex: str,
    *,
    citation_map: dict[str, Any],
    plot_assets_index: dict[str, Any],
    figures_dir: str | None,
    claim_map: dict[str, Any] | None,
) -> tuple[str, dict[str, str]]:
    latex = _ensure_bibliography_hook(latex, citation_map)
    latex = _normalize_generated_plot_paths(latex, plot_assets_index)
    latex = _normalize_source_figure_paths(latex, figures_dir)
    latex = _ensure_generated_plot_usage(latex, plot_assets_index)
    latex = _stabilize_figure_float_placement(latex)
    latex = _remove_material_packet_sections(latex)
    latex = _ensure_discussion_section_for_claim_boundaries(latex, claim_map)
    latex = _ensure_required_claim_scope_notes(latex, claim_map)
    return canonicalize_citation_keys(latex, citation_map)
