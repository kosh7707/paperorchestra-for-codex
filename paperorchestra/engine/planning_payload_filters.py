from __future__ import annotations

from typing import Any


def _filter_planning_payloads_for_sections(
    narrative_plan: dict[str, Any],
    claim_map: dict[str, Any],
    citation_placement_plan: dict[str, Any],
    section_names: list[str] | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if not section_names:
        return narrative_plan, claim_map, citation_placement_plan
    wanted = {name.strip().lower() for name in section_names if name.strip()}
    claims = [
        claim
        for claim in claim_map.get("claims", [])
        if isinstance(claim, dict) and str(claim.get("target_section") or "").strip().lower() in wanted
    ]
    claim_ids = {str(claim.get("id")) for claim in claims}
    narrative = dict(narrative_plan)
    narrative["section_roles"] = [
        role
        for role in narrative_plan.get("section_roles", [])
        if isinstance(role, dict) and str(role.get("section_title") or "").strip().lower() in wanted
    ]
    narrative["story_beats"] = [
        beat
        for beat in narrative_plan.get("story_beats", [])
        if isinstance(beat, dict) and str(beat.get("target_section") or "").strip().lower() in wanted
    ]
    claim_payload = dict(claim_map)
    claim_payload["claims"] = claims
    citation_payload = dict(citation_placement_plan)
    citation_payload["placements"] = [
        placement
        for placement in citation_placement_plan.get("placements", [])
        if isinstance(placement, dict)
        and (
            str(placement.get("target_section") or "").strip().lower() in wanted
            or str(placement.get("claim_id") or "") in claim_ids
        )
    ]
    return narrative, claim_payload, citation_payload
