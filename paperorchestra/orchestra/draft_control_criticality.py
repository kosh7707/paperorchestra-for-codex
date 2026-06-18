from __future__ import annotations

from paperorchestra.orchestra.draft_control_models import (
    HIGH_CRITICAL_CLAIM_TYPES,
    HIGH_CRITICAL_GRAPH_ROLES,
    MEDIUM_CRITICAL_CLAIM_TYPES,
    ClaimSignal,
)


def claim_signal_criticality(claim: ClaimSignal) -> str:
    if claim.claim_type in HIGH_CRITICAL_CLAIM_TYPES or claim.graph_role in HIGH_CRITICAL_GRAPH_ROLES:
        return "high"
    if claim.claim_type in MEDIUM_CRITICAL_CLAIM_TYPES:
        return "medium"
    return "low"
