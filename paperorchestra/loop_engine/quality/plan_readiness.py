from __future__ import annotations

from typing import Any

_REQUIRED_PASS_TIERS = ("tier_0_preconditions", "tier_1_structural", "tier_2_claim_safety", "tier_3_scholarly_quality")


def _quality_eval_ready(quality_eval: dict[str, Any], *, accept_mixed_provenance: bool) -> bool:
    tiers = quality_eval.get("tiers") if isinstance(quality_eval, dict) else {}
    if not isinstance(tiers, dict):
        return False
    if any(not isinstance(tiers.get(key), dict) or tiers[key].get("status") != "pass" for key in _REQUIRED_PASS_TIERS):
        return False
    provenance = quality_eval.get("provenance_trust") if isinstance(quality_eval.get("provenance_trust"), dict) else {}
    provenance_level = provenance.get("level")
    mixed_acceptance = provenance.get("mixed_acceptance") if isinstance(provenance.get("mixed_acceptance"), dict) else {}
    return provenance_level == "live" or (
        provenance_level == "mixed"
        and accept_mixed_provenance
        and mixed_acceptance.get("status") == "pass"
    )
