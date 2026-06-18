from __future__ import annotations

from typing import Any

from paperorchestra.core.boundary import sanitize_author_facing_text
from paperorchestra.manuscript.citations import canonical_citation_map

from .prompt_markup import _prompt_compact_text


def _compact_outline_for_prompt(outline: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(outline, dict):
        return outline
    section_plan = []
    for item in outline.get("section_plan", [])[:8]:
        if not isinstance(item, dict):
            continue
        compact_item: dict[str, Any] = {"section_title": item.get("section_title")}
        subsections = []
        for subsection in item.get("subsections", [])[:2]:
            if not isinstance(subsection, dict):
                continue
            compact_subsection = {
                "subsection_title": subsection.get("subsection_title"),
                "content_bullets": subsection.get("content_bullets", [])[:1],
                "citation_hints": subsection.get("citation_hints", [])[:1],
            }
            subsections.append(compact_subsection)
        compact_item["subsections"] = subsections
        section_plan.append(compact_item)
    return {"section_plan": section_plan}


def _compact_intro_related_plan_for_prompt(plan: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(plan, dict):
        return plan
    compact: dict[str, Any] = {}
    intro = plan.get("introduction_strategy")
    if isinstance(intro, dict):
        compact["introduction_strategy"] = {
            "opening_frame": sanitize_author_facing_text(str(intro.get("hook_hypothesis") or ""), fallback=""),
            "problem_gap": sanitize_author_facing_text(str(intro.get("problem_gap_hypothesis") or ""), fallback=""),
            "background_topics": [
                sanitize_author_facing_text(str(item), fallback="")
                for item in (intro.get("search_directions") or [])[:3]
                if str(item).strip()
            ],
        }
    related = plan.get("related_work_strategy")
    if isinstance(related, dict):
        subsections = []
        for subsection in related.get("subsections", [])[:4]:
            if not isinstance(subsection, dict):
                continue
            subsections.append(
                {
                    "subsection_title": subsection.get("subsection_title"),
                    "methodology_cluster": sanitize_author_facing_text(str(subsection.get("methodology_cluster") or ""), fallback=""),
                    "comparative_context_goal": sanitize_author_facing_text(str(subsection.get("sota_investigation_mission") or ""), fallback=""),
                    "limitations_to_discuss": sanitize_author_facing_text(str(subsection.get("limitation_hypothesis") or ""), fallback=""),
                    "bridge_to_our_method": sanitize_author_facing_text(str(subsection.get("bridge_to_our_method") or ""), fallback=""),
                }
            )
        compact["related_work_strategy"] = {
            "overview": sanitize_author_facing_text(str(related.get("overview") or ""), fallback=""),
            "subsections": subsections,
        }
    return compact


def _compact_plot_manifest_for_prompt(plot_manifest: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(plot_manifest, dict):
        return plot_manifest
    figures = []
    for figure in plot_manifest.get("figures", [])[:8]:
        if not isinstance(figure, dict):
            continue
        figures.append(
            {
                "figure_id": figure.get("figure_id"),
                "title": _prompt_compact_text(str(figure.get("title") or ""), head_chars=120, tail_chars=0),
                "caption": _prompt_compact_text(str(figure.get("caption") or ""), head_chars=180, tail_chars=0),
                "plot_type": figure.get("plot_type"),
                "aspect_ratio": figure.get("aspect_ratio"),
            }
        )
    return {"figures": figures}


def _compact_plot_assets_for_prompt(plot_assets_index: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(plot_assets_index, dict):
        return plot_assets_index
    assets = []
    for asset in plot_assets_index.get("assets", [])[:8]:
        if not isinstance(asset, dict):
            continue
        assets.append(
            {
                "figure_id": asset.get("figure_id"),
                "title": _prompt_compact_text(str(asset.get("title") or ""), head_chars=120, tail_chars=0),
                "caption": _prompt_compact_text(str(asset.get("caption") or ""), head_chars=180, tail_chars=0),
                "filename": asset.get("filename"),
                "latex_snippet_path": asset.get("latex_snippet_path"),
                "plot_type": asset.get("plot_type"),
            }
        )
    return {"assets": assets}


def _compact_citation_map_for_prompt(
    citation_map: dict[str, Any],
    *,
    title_limit: int = 140,
    abstract_limit: int = 220,
    max_authors: int = 4,
    include_abstract: bool = True,
    include_authors: bool = True,
    include_year: bool = True,
    include_venue: bool = True,
    include_provenance: bool = True,
    include_origin: bool = True,
    include_matched_query: bool = True,
) -> dict[str, Any]:
    citation_map = canonical_citation_map(citation_map)
    compact: dict[str, Any] = {}
    for key, value in citation_map.items():
        if not isinstance(value, dict):
            compact[key] = value
            continue
        authors = value.get("authors")
        if include_authors and isinstance(authors, list):
            compact_authors = authors[:max_authors]
        elif include_authors:
            compact_authors = authors
        else:
            compact_authors = None
        abstract = value.get("abstract")
        if include_abstract and isinstance(abstract, str):
            compact_abstract = _prompt_compact_text(abstract, head_chars=abstract_limit, tail_chars=0)
        elif include_abstract:
            compact_abstract = abstract
        else:
            compact_abstract = None
        provenance = value.get("provenance")
        title = value.get("title")
        if isinstance(title, str):
            title = _prompt_compact_text(title, head_chars=title_limit, tail_chars=0)
        entry = {"title": title}
        if include_authors:
            entry["authors"] = compact_authors
        if include_abstract:
            entry["abstract"] = compact_abstract
        if include_year:
            entry["year"] = value.get("year")
        if include_venue:
            entry["venue"] = value.get("venue")
        if include_provenance:
            entry["provenance"] = provenance.get("source") if isinstance(provenance, dict) else provenance
        if include_origin:
            entry["origin"] = value.get("origin")
        if include_matched_query:
            entry["matched_query"] = value.get("matched_query")
        compact[key] = entry
    return compact
