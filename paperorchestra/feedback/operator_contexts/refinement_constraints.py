from __future__ import annotations

from typing import Any

from paperorchestra.feedback.operator_contract import OPERATOR_REFINEMENT_FORBIDDEN_NEW_TIER2_CODES

_HARD_CONSTRAINTS = [
    "Use only bibliography keys already present in citation_map.json; do not add new bibliography keys.",
    "Do not use dense citation bundles to hide weak support; split or role-clarify them when they obscure claim support.",
    "Do not introduce weak, unsupported, manual-check, metadata-only, or insufficient-evidence citation support.",
    "Do not introduce new high-risk uncited claims; scope, delete, or ground existing high-risk claims instead.",
    "Reduce duplicate-support and claim-support issues; never make their counts worse.",
]


def _operator_refinement_constraints(
    quality_eval_payload: dict[str, Any] | None,
    citation_integrity_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    before_failing_codes = sorted(
        dict.fromkeys(
            [
                *_quality_tier2_failing_codes(quality_eval_payload),
                *_citation_integrity_failing_codes(citation_integrity_payload),
            ]
        )
    )
    return {
        "before_failing_codes": before_failing_codes,
        "forbidden_new_tier2_codes": sorted(OPERATOR_REFINEMENT_FORBIDDEN_NEW_TIER2_CODES),
        "hard_constraints": list(_HARD_CONSTRAINTS),
    }


def _quality_tier2_failing_codes(payload: dict[str, Any] | None) -> list[str]:
    if not isinstance(payload, dict):
        return []
    tiers = payload.get("tiers") if isinstance(payload.get("tiers"), dict) else {}
    tier2 = tiers.get("tier_2_claim_safety") if isinstance(tiers.get("tier_2_claim_safety"), dict) else {}
    return [str(code) for code in tier2.get("failing_codes") or [] if str(code).strip()]


def _citation_integrity_failing_codes(payload: dict[str, Any] | None) -> list[str]:
    if not isinstance(payload, dict):
        return []
    return [str(code) for code in payload.get("failing_codes") or [] if str(code).strip()]
