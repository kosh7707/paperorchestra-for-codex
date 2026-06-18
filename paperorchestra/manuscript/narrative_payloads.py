from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.boundary import normalized_claim_projection
from paperorchestra.manuscript.narrative_claim_map import build_citation_plan, build_claim_map, citation_placements
from paperorchestra.manuscript.narrative_claims import _first_key, build_claims
from paperorchestra.manuscript.narrative_context import PlanningContext, load_planning_context
from paperorchestra.manuscript.narrative_plan_builders import (
    CONTRIBUTION_BOUNDARY,
    FORBIDDEN_NARRATIVE_CLAIMS,
    PLANNING_THESIS,
    SECTION_ROLE_TEXT,
    _coverage_requirements_for_section,
    _must_cover_for_section,
    build_narrative_plan,
    build_section_roles,
    build_story_beats,
)
from paperorchestra.manuscript.narrative_sections import section_targets


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


__all__ = [
    "CONTRIBUTION_BOUNDARY",
    "FORBIDDEN_NARRATIVE_CLAIMS",
    "PLANNING_THESIS",
    "PlanningContext",
    "SECTION_ROLE_TEXT",
    "_coverage_requirements_for_section",
    "_must_cover_for_section",
    "build_citation_plan",
    "build_claim_map",
    "build_narrative_plan",
    "build_planning_payloads",
    "build_section_roles",
    "build_story_beats",
    "citation_placements",
    "load_planning_context",
]
