from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.boundary import normalized_claim_projection
from paperorchestra.manuscript.narrative_sources import _anchor


def _claim(
    *,
    idx: int,
    text: str,
    claim_type: str,
    grounding: str,
    target_section: str,
    source_path: str | Path | None,
    excerpt: str,
    coverage_groups: list[list[str]],
    required: bool = True,
    citation_keys: list[str] | None = None,
    risk: str = "medium",
    machine_obligation: str | None = None,
    authorial_claim: str | None = None,
    scope_note: str | None = None,
) -> dict[str, Any]:
    claim: dict[str, Any] = {
        "id": f"claim-{idx:03d}",
        "text": authorial_claim or text,
        "claim_type": claim_type,
        "grounding": grounding,
        "source_refs": [str(source_path)] if source_path else [],
        "target_section": target_section,
        "citation_keys": citation_keys or [],
        "risk": risk,
        "required": required,
        "coverage_terms": sorted({term for group in coverage_groups for term in group}),
        "coverage_groups": coverage_groups,
        "evidence_anchors": [_anchor(source_path, excerpt)] if (required or excerpt) else [],
    }
    if machine_obligation:
        claim["machine_obligation"] = machine_obligation
    if authorial_claim:
        claim["authorial_claim"] = authorial_claim
    if scope_note:
        claim["scope_note"] = scope_note
    projection = normalized_claim_projection(claim)
    claim.setdefault("authorial_claim", projection["authorial_claim"])
    claim.setdefault("scope_note", projection["scope_note"])
    return claim
