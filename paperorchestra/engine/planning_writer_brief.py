from __future__ import annotations

import json
from typing import Any

from paperorchestra.core.boundary import assert_author_facing_payload, normalized_claim_projection, sanitize_author_facing_text
from paperorchestra.core.errors import ContractError
from paperorchestra.engine.prompt_context import _data_block, _prompt_compact_text


def _writer_brief_from_planning(
    narrative_plan: dict[str, Any],
    claim_map: dict[str, Any],
    citation_placement_plan: dict[str, Any],
) -> dict[str, Any]:
    """Project planning artifacts into an author-facing prose brief."""

    claims_by_section = _claims_by_section_for_writer_brief(claim_map)
    brief = {
        "thesis": _prompt_compact_text(
            sanitize_author_facing_text(
                str(narrative_plan.get("thesis") or ""),
                fallback="Build a coherent scholarly draft that preserves the paper's stated claims, scope, and citation positioning.",
            ),
            head_chars=500,
            tail_chars=0,
        ),
        "contribution_boundary": [
            sanitize_author_facing_text(str(item), fallback="State evidence limits as ordinary scholarly assumptions, scope, and limitations.")
            for item in (narrative_plan.get("contribution_boundary") or [])
            if str(item).strip()
        ],
        "section_roles": _section_roles_for_writer_brief(narrative_plan, claims_by_section),
        "citation_guidance": _citation_guidance_for_writer_brief(citation_placement_plan),
        "authoring_rules": [
            "Write only scholarly paper prose.",
            "Use external citations for background, standards, baselines, and contrast; keep core method, proof, and result claims tied to technical evidence.",
            "State limitations as normal scholarly scope conditions rather than process disclaimers.",
        ],
    }
    _validate_author_facing_writer_brief(brief)
    return brief


def _claims_by_section_for_writer_brief(claim_map: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    claims_by_section: dict[str, list[dict[str, Any]]] = {}
    for claim in claim_map.get("claims") or []:
        if not isinstance(claim, dict):
            continue
        projection = normalized_claim_projection(claim)
        section = str(projection.get("target_section") or "").strip() or "Unassigned"
        grounding = str(projection.get("grounding") or "").strip()
        grounding_label = {
            "source_material": "technical_evidence",
            "experimental_log": "measurement_log",
            "human_boundary": "author_scope_constraints",
            "verified_citation": "verified_background_literature",
        }.get(grounding, grounding or None)
        supporting_evidence = _safe_supporting_evidence(claim)
        claims_by_section.setdefault(section, []).append(
            {
                "claim": _prompt_compact_text(str(projection.get("authorial_claim") or ""), head_chars=260, tail_chars=0),
                "type": projection.get("claim_type"),
                "grounding": grounding_label,
                "required": bool(projection.get("required", True)),
                "risk": projection.get("risk"),
                "supporting_evidence": supporting_evidence,
                "supporting_excerpt": supporting_evidence[0]["excerpt"] if supporting_evidence else "",
                "coverage_terms": projection.get("coverage_groups") or [],
            }
        )
    return claims_by_section


def _safe_supporting_evidence(claim: dict[str, Any]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for anchor in claim.get("evidence_anchors") or []:
        if not isinstance(anchor, dict):
            continue
        excerpt = sanitize_author_facing_text(str(anchor.get("evidence_excerpt") or anchor.get("excerpt") or ""), fallback="")
        if not excerpt:
            continue
        item: dict[str, Any] = {"excerpt": _prompt_compact_text(excerpt, head_chars=360, tail_chars=0)}
        line_start = anchor.get("line_start")
        line_end = anchor.get("line_end")
        if isinstance(line_start, int) and isinstance(line_end, int) and line_start > 0 and line_end >= line_start:
            item["location"] = f"lines {line_start}-{line_end}"
        evidence.append(item)
    legacy_excerpt = sanitize_author_facing_text(str(claim.get("excerpt") or ""), fallback="")
    if legacy_excerpt and not evidence:
        evidence.append({"excerpt": _prompt_compact_text(legacy_excerpt, head_chars=360, tail_chars=0)})
    return evidence


def _citation_guidance_for_writer_brief(citation_placement_plan: dict[str, Any]) -> list[dict[str, Any]]:
    guidance: list[dict[str, Any]] = []
    for placement in citation_placement_plan.get("placements") or []:
        if not isinstance(placement, dict):
            continue
        guidance.append(
            {
                "section": placement.get("target_section"),
                "citation_keys": placement.get("citation_keys") or [],
                "purpose": _prompt_compact_text(str(placement.get("purpose") or placement.get("rationale") or ""), head_chars=220, tail_chars=0),
            }
        )
    return guidance


def _section_roles_for_writer_brief(
    narrative_plan: dict[str, Any],
    claims_by_section: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    section_roles = []
    for role in narrative_plan.get("section_roles") or []:
        if not isinstance(role, dict):
            continue
        title = str(role.get("section_title") or "").strip()
        must_cover = [str(item) for item in role.get("must_cover") or [] if str(item).strip()]
        required_claims = claims_by_section.get(title, [])
        if required_claims:
            must_cover = [claim["claim"] for claim in required_claims if claim.get("claim")]
        section_roles.append(
            {
                "section": title,
                "role": _prompt_compact_text(
                    sanitize_author_facing_text(
                        str(role.get("role") or ""),
                        fallback="Develop this section from stated evidence, assumptions, and assigned citations.",
                    ),
                    head_chars=260,
                    tail_chars=0,
                ),
                "must_cover": must_cover,
                "must_not_claim": role.get("must_not_claim") or [],
                "required_claims": required_claims,
            }
        )
    return section_roles


def _validate_author_facing_writer_brief(brief: dict[str, Any]) -> dict[str, Any]:
    try:
        assert_author_facing_payload(brief, label="author_facing_writer_brief.json")
    except ValueError as exc:
        raise ContractError(str(exc)) from exc
    return brief


def _author_facing_writer_brief_block(brief: dict[str, Any]) -> str:
    return _data_block(
        "scholarly_authoring_brief",
        json.dumps(_validate_author_facing_writer_brief(brief), indent=2, ensure_ascii=False),
    )
