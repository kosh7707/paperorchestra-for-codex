from __future__ import annotations

from typing import Any

from paperorchestra.manuscript.narrative_contracts import NARRATIVE_PLAN_SCHEMA_VERSION

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
