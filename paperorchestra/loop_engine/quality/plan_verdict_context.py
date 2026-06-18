from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .history_eval import _failing_codes_from_quality_eval


@dataclass(frozen=True)
class PlanVerdictContext:
    quality_eval: dict[str, Any]
    cross: dict[str, Any]
    budget: dict[str, Any]
    regression: dict[str, Any]
    tiers: dict[str, Any]
    failing_codes: list[str]
    tier0_codes: set[str]
    tier1_codes: set[str]
    non_reviewable_codes: set[str]

    @classmethod
    def from_quality_eval(cls, quality_eval: dict[str, Any]) -> "PlanVerdictContext":
        cross = quality_eval.get("cross_iteration") or {}
        budget = cross.get("budget") or {}
        regression = cross.get("regression") or {}
        tiers = quality_eval.get("tiers") if isinstance(quality_eval.get("tiers"), dict) else {}
        return cls(
            quality_eval=quality_eval,
            cross=cross,
            budget=budget,
            regression=regression,
            tiers=tiers,
            failing_codes=_failing_codes_from_quality_eval(quality_eval),
            tier0_codes=_tier_failing_codes(tiers, "tier_0_preconditions"),
            tier1_codes=_tier_failing_codes(tiers, "tier_1_structural"),
            non_reviewable_codes=_non_reviewable_codes(quality_eval),
        )


def _tier_failing_codes(tiers: dict[str, Any], tier_name: str) -> set[str]:
    tier = tiers.get(tier_name)
    return set(tier.get("failing_codes") or []) if isinstance(tier, dict) else set()


def _non_reviewable_codes(quality_eval: dict[str, Any]) -> set[str]:
    non_reviewable = quality_eval.get("non_reviewable")
    return set(non_reviewable.get("failing_codes") or []) if isinstance(non_reviewable, dict) else set()
