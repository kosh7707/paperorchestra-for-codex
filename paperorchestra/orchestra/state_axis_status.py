from __future__ import annotations

from typing import Any

_MATERIAL_STATUS = {
    "missing": "missing",
    "inventory_needed": "insufficient",
    "inventoried_insufficient": "insufficient",
    "inventoried_sufficient": "ready",
    "blocked": "blocked",
}

_CITATION_STATUS = {
    "not_checked": "not_checked",
    "unknown_refs": "unknown_refs",
    "unsupported_critical": "unsupported",
    "warnings_only": "warnings",
    "supported": "supported",
}

_FIGURE_STATUS = {
    "not_checked": "not_checked",
    "inventory_needed": "needs_inventory",
    "placeholder_only": "placeholder",
    "matched": "matched",
    "human_finalization_needed": "human_polish",
    "blocked": "blocked",
}


def derive_five_axis_status(state: Any) -> dict[str, str]:
    facets = state.facets
    return {
        "materials": _materials_status(facets),
        "claims": _claims_status(facets),
        "citations": _CITATION_STATUS.get(facets.citations, "not_checked"),
        "figures": _FIGURE_STATUS.get(facets.figures, "not_checked"),
        "readiness": state.readiness.label,
    }


def _materials_status(facets: Any) -> str:
    status = _MATERIAL_STATUS.get(facets.material, "missing")
    if facets.source_digest == "ready" and status == "ready":
        return "ready"
    return status


def _claims_status(facets: Any) -> str:
    if facets.claims == "conflict":
        return "conflict"
    if facets.evidence in {"research_needed", "durable_research_needed"}:
        return "needs_research"
    if facets.claims == "validated" and facets.evidence == "supported":
        return "supported"
    if facets.claims == "blocked" or facets.evidence == "blocked":
        return "blocked"
    return "missing"
