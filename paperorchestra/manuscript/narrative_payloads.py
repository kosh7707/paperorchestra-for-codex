from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paperorchestra.core.boundary import normalized_claim_projection
from paperorchestra.core.io import read_json
from paperorchestra.core.session import load_session
from paperorchestra.manuscript.narrative_claims import _first_key, build_claims
from paperorchestra.manuscript.narrative_contracts import (
    CITATION_PLACEMENT_PLAN_SCHEMA_VERSION,
    CLAIM_MAP_SCHEMA_VERSION,
    NARRATIVE_PLAN_SCHEMA_VERSION,
    planning_source_hashes,
)
from paperorchestra.manuscript.narrative_sections import _section_titles, default_sections, section_targets
from paperorchestra.manuscript.narrative_sources import _planning_source_text, _read_text

PLANNING_THESIS = (
    "Build a coherent scholarly draft that preserves the paper's method, proof, benchmark, "
    "and limitation scope while using verified references for positioning."
)
CONTRIBUTION_BOUNDARY = [
    "Keep method, proof, benchmark, and limitation claims within the stated assumptions and evidence.",
    (
        "Use external citations for background, standards, baselines, and contrast "
        "rather than unsupported core results."
    ),
]
SECTION_ROLE_TEXT = (
    "Develop this section from the technical evidence, stated assumptions, and assigned citations "
    "without adding unsupported claims."
)
FORBIDDEN_NARRATIVE_CLAIMS = [
    "submission ready",
    "camera-ready",
    "unqualified automatic acceptance",
    "human review is unnecessary",
    "guaranteed scientific correctness",
]


@dataclass(frozen=True)
class PlanningContext:
    state: Any
    citation_map: dict[str, Any]
    sections: list[str]
    log_planning_text: str
    template_planning_text: str
    planning_text: str
    author_source_text: str
    source_hashes: dict[str, str | None]


def build_planning_payloads(cwd: str | Path | None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    context = load_planning_context(cwd)
    citation_key = _first_key(context.citation_map)
    targets = section_targets(context.sections, citation_key=citation_key)
    claims = build_claims(
        state=context.state,
        planning_text=context.planning_text,
        author_source_text=context.author_source_text,
        template_planning_text=context.template_planning_text,
        log_planning_text=context.log_planning_text,
        citation_map=context.citation_map,
        targets=targets,
    )
    projections = [normalized_claim_projection(claim) for claim in claims]
    return (
        build_narrative_plan(
            sections=context.sections,
            claims=claims,
            projections=projections,
            source_hashes=context.source_hashes,
        ),
        build_claim_map(claims=claims, source_hashes=context.source_hashes),
        build_citation_plan(claims=claims, source_hashes=context.source_hashes),
    )


def load_planning_context(cwd: str | Path | None) -> PlanningContext:
    state = load_session(cwd)
    outline = read_json(state.artifacts.outline_json) if state.artifacts.outline_json else {"section_plan": []}
    citation_map = read_json(state.artifacts.citation_map_json) if state.artifacts.citation_map_json else {}
    idea_planning_text = _planning_source_text(_read_text(state.inputs.idea_path), preserve_numeric_percent=True)
    log_planning_text = _planning_source_text(
        _read_text(state.inputs.experimental_log_path),
        preserve_numeric_percent=True,
    )
    template_text = _read_text(state.inputs.template_path)
    template_planning_text = _planning_source_text(template_text)
    sections = _section_titles(outline, template_text) or default_sections()
    return PlanningContext(
        state=state,
        citation_map=citation_map if isinstance(citation_map, dict) else {},
        sections=sections,
        log_planning_text=log_planning_text,
        template_planning_text=template_planning_text,
        planning_text="\n".join([idea_planning_text, log_planning_text, template_planning_text]),
        author_source_text="\n".join([idea_planning_text, log_planning_text]),
        source_hashes=planning_source_hashes(cwd),
    )


def build_narrative_plan(
    *,
    sections: list[str],
    claims: list[dict[str, Any]],
    projections: list[dict[str, Any]],
    source_hashes: dict[str, str | None],
) -> dict[str, Any]:
    return {
        "schema_version": NARRATIVE_PLAN_SCHEMA_VERSION,
        "source_hashes": source_hashes,
        "thesis": PLANNING_THESIS,
        "contribution_boundary": CONTRIBUTION_BOUNDARY,
        "section_roles": build_section_roles(sections=sections, claims=claims, projections=projections),
        "story_beats": build_story_beats(projections),
    }


def build_section_roles(
    *,
    sections: list[str],
    claims: list[dict[str, Any]],
    projections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    projections_by_id = {projection["id"]: projection for projection in projections}
    return [
        {
            "section_title": title,
            "role": SECTION_ROLE_TEXT,
            "must_cover": _must_cover_for_section(title, claims=claims, projections_by_id=projections_by_id),
            "coverage_requirements": _coverage_requirements_for_section(title, projections),
            "must_not_claim": FORBIDDEN_NARRATIVE_CLAIMS,
        }
        for title in sections
    ]


def _must_cover_for_section(
    title: str,
    *,
    claims: list[dict[str, Any]],
    projections_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    return [
        projections_by_id[str(claim.get("id") or "")]["authorial_claim"]
        for claim in claims
        if claim.get("target_section") == title
        and claim.get("required")
        and str(claim.get("id") or "") in projections_by_id
    ]


def _coverage_requirements_for_section(title: str, projections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "claim_id": projection["id"],
            "authorial_claim": projection["authorial_claim"],
            "coverage_terms": projection["coverage_terms"],
            "coverage_groups": projection["coverage_groups"],
        }
        for projection in projections
        if projection.get("target_section") == title and projection.get("required")
    ]


def build_story_beats(projections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "order": i + 1,
            "beat": projection["authorial_claim"],
            "target_section": projection["target_section"],
            "evidence_source": projection["grounding"],
            "coverage_terms": projection["coverage_terms"],
            "coverage_groups": projection["coverage_groups"],
        }
        for i, projection in enumerate(projections)
        if projection.get("required")
    ]


def build_claim_map(*, claims: list[dict[str, Any]], source_hashes: dict[str, str | None]) -> dict[str, Any]:
    return {
        "schema_version": CLAIM_MAP_SCHEMA_VERSION,
        "source_hashes": source_hashes,
        "claims": claims,
    }


def build_citation_plan(*, claims: list[dict[str, Any]], source_hashes: dict[str, str | None]) -> dict[str, Any]:
    return {
        "schema_version": CITATION_PLACEMENT_PLAN_SCHEMA_VERSION,
        "source_hashes": source_hashes,
        "placements": citation_placements(claims),
    }


def citation_placements(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "claim_id": claim["id"],
            "target_section": claim["target_section"],
            "citation_keys": claim["citation_keys"],
            "support_role": "background" if claim["claim_type"] == "positioning" else "contrast",
            "placement_rule": "same_sentence_or_adjacent",
        }
        for claim in claims
        if claim.get("citation_keys")
    ]
