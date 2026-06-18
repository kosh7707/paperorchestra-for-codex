from __future__ import annotations

from typing import Any


def _failing_codes_from_quality_eval(quality_eval: dict[str, Any]) -> list[str]:
    codes: list[str] = []
    non_reviewable = quality_eval.get("non_reviewable") if isinstance(quality_eval, dict) else {}
    if isinstance(non_reviewable, dict):
        for code in non_reviewable.get("failing_codes") or []:
            codes.append(str(code))
    tiers = quality_eval.get("tiers") if isinstance(quality_eval, dict) else {}
    if not isinstance(tiers, dict):
        return codes
    for key, tier in tiers.items():
        if not str(key).startswith("tier_") or not isinstance(tier, dict):
            continue
        status = tier.get("status")
        if status not in {"fail", "warn"}:
            continue
        for code in tier.get("failing_codes") or []:
            codes.append(str(code))
    return sorted(dict.fromkeys(codes))


def _tier_statuses(quality_eval: dict[str, Any]) -> dict[str, str]:
    statuses: dict[str, str] = {}
    tiers = quality_eval.get("tiers") if isinstance(quality_eval, dict) else {}
    if isinstance(tiers, dict):
        for key, tier in tiers.items():
            if isinstance(tier, dict) and str(key).startswith("tier_"):
                statuses[key] = str(tier.get("status"))
    return statuses
