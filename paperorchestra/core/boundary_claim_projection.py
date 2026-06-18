from __future__ import annotations

from typing import Any

from paperorchestra.core.boundary_claim_text import authorial_claim_text, scope_note_text
from paperorchestra.core.boundary_claim_values import normalized_coverage_groups


def normalized_claim_projection(claim: dict[str, Any]) -> dict[str, Any]:
    coverage_groups = normalized_coverage_groups(claim)
    return {
        "id": str(claim.get("id") or ""),
        "target_section": str(claim.get("target_section") or ""),
        "claim_type": claim.get("claim_type"),
        "grounding": claim.get("grounding"),
        "required": bool(claim.get("required", True)),
        "risk": claim.get("risk"),
        "authorial_claim": authorial_claim_text(claim),
        "scope_note": scope_note_text(claim),
        "coverage_groups": coverage_groups,
        "coverage_terms": sorted({term for group in coverage_groups for term in group}),
        "machine_obligation": str(claim.get("machine_obligation") or "").strip(),
    }


def projection_for_claims(claims: Any) -> list[dict[str, Any]]:
    if not isinstance(claims, list):
        return []
    return [normalized_claim_projection(claim) for claim in claims if isinstance(claim, dict)]
