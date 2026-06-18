from __future__ import annotations

from typing import Any

from paperorchestra.orchestra.state_models import ReadinessSummary


def derive_readiness(state: Any) -> ReadinessSummary:
    facets = state.facets
    if state.hard_gates.status == "fail":
        return ReadinessSummary("not_ready", "blocked", "Hard gate failures block readiness.")
    if state.author_override and (facets.claims == "conflict" or facets.evidence in {"unresolved", "blocked"}):
        return ReadinessSummary("not_ready", "blocked", "Author override conflicts with current evidence.")
    if facets.omx == "required_missing":
        return ReadinessSummary("not_ready", "blocked", "Strict OMX evidence is required but missing.")
    if facets.figures in {"placeholder_only", "inventory_needed", "blocked"} and facets.quality in {
        "near_ready",
        "human_finalization_candidate",
    }:
        return ReadinessSummary("not_ready", "blocked", "Figure gate prevents final readiness.")
    if facets.session == "no_session" and facets.material == "missing":
        return ReadinessSummary("needs_material", "blocked", "No session or material has been provided.")
    if facets.material == "inventory_needed":
        return ReadinessSummary("material_inventory_needed", "blocked", "Material must be inventoried before drafting.")
    if facets.evidence in {"research_needed", "durable_research_needed"}:
        return ReadinessSummary("research_needed", "blocked", "Machine-solvable evidence work remains.")
    if facets.claims == "conflict" or facets.interaction == "human_needed":
        return ReadinessSummary("human_needed", "blocked", "Author judgment is required.")
    if facets.quality == "repairable":
        return ReadinessSummary("repair_needed", "blocked", "Repair loop is required.")
    if facets.quality == "hard_gate_failed":
        return ReadinessSummary("not_ready", "blocked", "Quality hard gate failed.")
    if facets.quality == "human_finalization_candidate" and state.hard_gates.status in {"pass", "unknown"}:
        return ReadinessSummary("ready_for_human_finalization", "ready", "Automation is ready for human finalization.")
    if (
        facets.material == "inventoried_sufficient"
        and facets.source_digest == "ready"
        and facets.claims == "validated"
        and facets.evidence == "supported"
        and facets.writing == "not_allowed"
    ):
        return ReadinessSummary("draft_blocked", "blocked", "Prewriting notice must be shown before drafting.")
    if facets.writing == "drafting_allowed":
        return ReadinessSummary("ready_for_drafting", "ready", "Drafting is allowed by current state.")
    if facets.session in {"draft_available", "compiled"}:
        return ReadinessSummary("not_ready", "blocked", "Draft exists but claim-safe quality readiness is not established.")
    return ReadinessSummary("not_ready", "blocked", "State is not ready.")


def derive_five_axis_status(state: Any) -> dict[str, str]:
    facets = state.facets
    materials = {
        "missing": "missing",
        "inventory_needed": "insufficient",
        "inventoried_insufficient": "insufficient",
        "inventoried_sufficient": "ready",
        "blocked": "blocked",
    }.get(facets.material, "missing")
    if facets.source_digest == "ready" and materials == "ready":
        materials = "ready"

    claims = "missing"
    if facets.claims == "conflict":
        claims = "conflict"
    elif facets.evidence in {"research_needed", "durable_research_needed"}:
        claims = "needs_research"
    elif facets.claims == "validated" and facets.evidence == "supported":
        claims = "supported"
    elif facets.claims == "blocked" or facets.evidence == "blocked":
        claims = "blocked"

    citations = {
        "not_checked": "not_checked",
        "unknown_refs": "unknown_refs",
        "unsupported_critical": "unsupported",
        "warnings_only": "warnings",
        "supported": "supported",
    }.get(facets.citations, "not_checked")

    figures = {
        "not_checked": "not_checked",
        "inventory_needed": "needs_inventory",
        "placeholder_only": "placeholder",
        "matched": "matched",
        "human_finalization_needed": "human_polish",
        "blocked": "blocked",
    }.get(facets.figures, "not_checked")

    return {
        "materials": materials,
        "claims": claims,
        "citations": citations,
        "figures": figures,
        "readiness": state.readiness.label,
    }
