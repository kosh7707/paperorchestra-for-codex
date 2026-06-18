from __future__ import annotations

from typing import Any


def quality_gate_verdict(blocked_dimensions: list[str], warning_dimensions: list[str], plan: dict[str, Any]) -> str:
    if blocked_dimensions:
        return "block"
    if warning_dimensions or plan.get("repair_actions"):
        return "repairable"
    return "pass"


def tier_status(quality_eval: dict[str, Any], tier_name: str) -> str:
    tiers = quality_eval.get("tiers") if isinstance(quality_eval.get("tiers"), dict) else {}
    tier = tiers.get(tier_name) if isinstance(tiers.get(tier_name), dict) else {}
    return str(tier.get("status") or "missing")


def tier_codes(quality_eval: dict[str, Any], tier_name: str) -> list[str]:
    tiers = quality_eval.get("tiers") if isinstance(quality_eval.get("tiers"), dict) else {}
    tier = tiers.get(tier_name) if isinstance(tiers.get(tier_name), dict) else {}
    return [str(code) for code in (tier.get("failing_codes") or []) if code]


def dimension(
    *,
    name: str,
    status: str,
    blocking: bool,
    failing_codes: list[str] | None = None,
    sources: list[str] | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "blocking": bool(blocking),
        "failing_codes": sorted(dict.fromkeys(failing_codes or [])),
        "sources": sources or [],
        "details": details or {},
    }


def repair_action_ids(plan: dict[str, Any], codes: set[str]) -> list[str]:
    action_ids: list[str] = []
    for action in plan.get("repair_actions") or []:
        if not isinstance(action, dict):
            continue
        if str(action.get("code") or "") in codes:
            action_id = str(action.get("id") or "")
            if action_id:
                action_ids.append(action_id)
    return sorted(dict.fromkeys(action_ids))
