from __future__ import annotations

from typing import Any

from paperorchestra.feedback.operator_contexts.text import _truncate_context_text


def _high_risk_claim_context(payload: dict[str, Any] | None, *, limit: int = 16) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    tiers = payload.get("tiers") if isinstance(payload.get("tiers"), dict) else {}
    tier2 = tiers.get("tier_2_claim_safety") if isinstance(tiers.get("tier_2_claim_safety"), dict) else {}
    checks = tier2.get("checks") if isinstance(tier2.get("checks"), dict) else {}
    sweep = checks.get("high_risk_claim_sweep") if isinstance(checks.get("high_risk_claim_sweep"), dict) else {}
    result: list[dict[str, Any]] = []
    for item in sweep.get("items") or []:
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "line": item.get("line"),
                "sentence": _truncate_context_text(item.get("sentence"), limit=900),
                "reason": _truncate_context_text(item.get("reason"), limit=500),
            }
        )
        if len(result) >= limit:
            break
    return result
