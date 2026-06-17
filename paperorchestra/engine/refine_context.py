from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json, read_text
from paperorchestra.core.session import review_path
from paperorchestra.engine.latex_postprocess import _reviewable_plot_assets_index, _reviewable_plot_manifest
from paperorchestra.engine.prompt_context import (
    _compact_citation_map_for_prompt,
    _prompt_compact_text,
    _read_inputs,
    _raise_if_strict_source_citations_unmapped,
    _source_critical_context_for_prompt,
    _strict_content_gates_enabled,
)
from paperorchestra.engine.refine_prompt import build_refinement_user_prompt
from paperorchestra.engine.section_scope import _expected_section_titles_from_outline


@dataclass(frozen=True)
class RefinementIterationContext:
    current_paper: str
    review_payload: dict[str, Any]
    citation_map: dict[str, Any]
    plot_manifest: dict[str, Any]
    plot_assets_index: dict[str, Any]
    expected_section_titles: list[str]
    strict_claim_safe_prompt: bool
    experimental_log_text: str
    candidate_iter: int
    previous_worklog: str
    prompt_plot_manifest: dict[str, Any]
    prompt_plot_assets_index: dict[str, Any]
    user_prompt: str


def build_refinement_iteration_context(
    cwd: str | Path | None,
    state: Any,
    *,
    claim_safe: bool,
    writer_brief: dict[str, Any] | None,
) -> RefinementIterationContext:
    current_paper = read_text(state.artifacts.paper_full_tex)
    review_payload = read_json(state.artifacts.latest_review_json)
    citation_map = read_json(state.artifacts.citation_map_json) if state.artifacts.citation_map_json else {}

    raw_plot_manifest = (
        read_json(state.artifacts.plot_manifest_json)
        if state.artifacts.plot_manifest_json
        else {"figures": []}
    )
    raw_plot_assets_index = (
        read_json(state.artifacts.plot_assets_json)
        if state.artifacts.plot_assets_json
        else {"assets": []}
    )
    plot_assets_index = _reviewable_plot_assets_index(raw_plot_assets_index)
    plot_manifest = _reviewable_plot_manifest(raw_plot_manifest, raw_plot_assets_index)

    outline = read_json(state.artifacts.outline_json) if state.artifacts.outline_json else {"section_plan": []}
    expected_section_titles = _expected_section_titles_from_outline(outline)

    inputs = _read_inputs(state)
    strict_claim_safe_prompt = _strict_content_gates_enabled(claim_safe=claim_safe)
    _raise_if_strict_source_citations_unmapped(
        inputs,
        citation_map,
        stage="refinement",
        strict_claim_safe=strict_claim_safe_prompt,
    )

    experimental_log_text = read_text(state.inputs.experimental_log_path)
    candidate_iter = state.refinement_iteration + 1
    previous_worklog_path = review_path(cwd, f"refinement_worklog.iter-{state.refinement_iteration:02d}.json")
    previous_worklog = read_text(previous_worklog_path) if previous_worklog_path.exists() else "{}"

    prompt_plot_manifest = _prompt_plot_manifest(plot_manifest)
    prompt_plot_assets_index = _prompt_plot_assets_index(plot_assets_index)
    user_prompt = build_refinement_user_prompt(
        paper_text=_prompt_compact_text(current_paper, head_chars=22000, tail_chars=4000),
        review_payload=review_payload,
        writer_brief=writer_brief or {},
        experimental_log_text=_prompt_compact_text(experimental_log_text, head_chars=8000, tail_chars=1500),
        source_critical_context=_source_critical_context_for_prompt(inputs),
        citation_map=_compact_citation_map_for_prompt(
            citation_map,
            include_abstract=strict_claim_safe_prompt,
            include_authors=False,
            include_year=strict_claim_safe_prompt,
            include_venue=strict_claim_safe_prompt,
            include_provenance=False,
            include_origin=False,
            include_matched_query=False,
        ),
        plot_manifest=prompt_plot_manifest,
        plot_assets_index=prompt_plot_assets_index,
        previous_worklog=previous_worklog,
    )
    return RefinementIterationContext(
        current_paper=current_paper,
        review_payload=review_payload,
        citation_map=citation_map,
        plot_manifest=plot_manifest,
        plot_assets_index=plot_assets_index,
        expected_section_titles=expected_section_titles,
        strict_claim_safe_prompt=strict_claim_safe_prompt,
        experimental_log_text=experimental_log_text,
        candidate_iter=candidate_iter,
        previous_worklog=previous_worklog,
        prompt_plot_manifest=prompt_plot_manifest,
        prompt_plot_assets_index=prompt_plot_assets_index,
        user_prompt=user_prompt,
    )


def _prompt_plot_manifest(plot_manifest: dict[str, Any]) -> dict[str, Any]:
    return {"figures": plot_manifest.get("figures", [])[:8]}


def _prompt_plot_assets_index(plot_assets_index: dict[str, Any]) -> dict[str, Any]:
    return {"assets": plot_assets_index.get("assets", [])[:8]}
