from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.core.boundary import sanitize_author_facing_text
from paperorchestra.core.io import read_text
from paperorchestra.domains import get_domain
from paperorchestra.engine.completion import _env_flag
from paperorchestra.manuscript.citations import CITE_COMMAND_RE, allowed_citation_keys, canonical_citation_map


def _read_inputs(state) -> dict[str, str]:
    return {
        "idea": read_text(state.inputs.idea_path),
        "experimental_log": read_text(state.inputs.experimental_log_path),
        "template": read_text(state.inputs.template_path),
        "guidelines": read_text(state.inputs.guidelines_path),
        "figures": _figure_listing(state.inputs.figures_dir),
    }


def _figure_listing(figures_dir: str | None) -> str:
    if not figures_dir:
        return "No figures directory provided."
    root = Path(figures_dir)
    if not root.exists():
        return f"Figures directory does not exist: {figures_dir}"
    files = [str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()]
    if not files:
        return "Figures directory is empty."
    return "\n".join(sorted(files))


def _source_grounding_text(inputs: dict[str, str]) -> str:
    return "\n\n".join(
        part
        for part in (
            inputs.get("experimental_log", ""),
            inputs.get("idea", ""),
            inputs.get("template", ""),
        )
        if part
    )


def _data_block(name: str, content: str) -> str:
    return f'<DATA_BLOCK name="{name}">\n{html.escape(content.strip())}\n</DATA_BLOCK>'


def _prompt_compact_text(
    text: str,
    *,
    head_chars: int,
    tail_chars: int = 0,
    marker: str = "[...truncated for prompt budget...]",
) -> str:
    if len(text) <= head_chars + tail_chars + len(marker):
        return text
    if tail_chars <= 0:
        return text[:head_chars].rstrip() + "\n" + marker
    return text[:head_chars].rstrip() + "\n" + marker + "\n" + text[-tail_chars:].lstrip()


def _strict_content_gates_enabled(*, claim_safe: bool = False) -> bool:
    return claim_safe or _env_flag("PAPERO_STRICT_CONTENT_GATES")


def _source_critical_context_for_prompt(
    inputs: dict[str, str],
    *,
    window_chars: int = 1400,
    max_blocks_per_kind: int = 3,
) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int, int]] = set()
    patterns = get_domain().source_critical_patterns
    for source_name in ("idea", "experimental_log", "template"):
        text = inputs.get(source_name) or ""
        if not text:
            continue
        for kind, pattern in patterns:
            count_for_kind = sum(1 for block in blocks if block["source"] == source_name and block["kind"] == kind)
            if count_for_kind >= max_blocks_per_kind:
                continue
            for match in pattern.finditer(text):
                count_for_kind = sum(1 for block in blocks if block["source"] == source_name and block["kind"] == kind)
                if count_for_kind >= max_blocks_per_kind:
                    break
                start = max(0, match.start() - window_chars // 2)
                end = min(len(text), match.end() + window_chars // 2)
                excerpt = text[start:end].strip()
                key = (source_name, kind, start, end)
                if not excerpt or key in seen:
                    continue
                seen.add(key)
                blocks.append(
                    {
                        "source": source_name,
                        "kind": kind,
                        "anchor": match.group(0),
                        "start_char": start,
                        "end_char": end,
                        "excerpt": excerpt,
                    }
                )
    return {
        "schema_version": "source-critical-context/1",
        "description": "Exact source spans selected to prevent prompt truncation from hiding critical material.",
        "blocks": blocks[:30],
    }


def _unknown_citation_key_counts(latex: str, citation_map: dict[str, Any]) -> dict[str, int]:
    if not citation_map:
        return {}
    allowed = allowed_citation_keys(citation_map)
    counts: dict[str, int] = {}
    for match in CITE_COMMAND_RE.finditer(latex):
        for key in [key.strip() for key in match.group(2).split(",") if key.strip()]:
            if key not in allowed:
                counts[key] = counts.get(key, 0) + 1
    return counts


def _raise_if_strict_source_citations_unmapped(
    inputs: dict[str, str],
    citation_map: dict[str, Any],
    *,
    stage: str,
    strict_claim_safe: bool,
) -> None:
    if not strict_claim_safe:
        return
    unknown = _unknown_citation_key_counts(_source_grounding_text(inputs), citation_map)
    if not unknown:
        return
    detail = ", ".join(f"{key}({count})" for key, count in sorted(unknown.items()))
    raise ContractError(
        f"{stage} claim-safe source packet contains citation keys that are not present in citation_map.json: {detail}. "
        "Import/map these source citations into the verified citation registry before claim-safe writing."
    )


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

