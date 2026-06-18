from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from paperorchestra.loop_engine.quality.gate_dimension_builders import (
    STORY_LOGIC_CODES,
    build_quality_gate_dimensions,
    citation_claim_safety_dimension,
    human_finalization_dimension,
    reproducibility_dimension,
    reviewer_acceptability_dimension,
    story_logic_dimension,
    structure_latex_dimension,
)
from paperorchestra.loop_engine.quality.gate_dimension_helpers import (
    dimension,
    quality_gate_verdict,
    repair_action_ids,
    tier_codes,
    tier_status,
)
from paperorchestra.loop_engine.quality.gate_profile_policy import QUALITY_GATE_PROFILES, normalize_profile, status_for_profile


@dataclass(frozen=True)
class QualityGateDimensionBundle:
    resolved_profile: str
    dimensions: dict[str, dict[str, Any]]
    blocked_dimensions: list[str]
    warning_dimensions: list[str]
    verdict: str


def build_quality_gate_dimension_bundle(
    quality_eval: dict[str, Any],
    plan: dict[str, Any],
    *,
    profile: str = "auto",
) -> QualityGateDimensionBundle:
    resolved_profile = normalize_profile(profile, quality_eval)
    dimensions = build_quality_gate_dimensions(quality_eval, plan, profile=resolved_profile)
    blocked_dimensions = [key for key, value in dimensions.items() if value.get("blocking")]
    warning_dimensions = [key for key, value in dimensions.items() if value.get("status") == "warn"]
    return QualityGateDimensionBundle(
        resolved_profile=resolved_profile,
        dimensions=dimensions,
        blocked_dimensions=blocked_dimensions,
        warning_dimensions=warning_dimensions,
        verdict=quality_gate_verdict(blocked_dimensions, warning_dimensions, plan),
    )


__all__ = [
    "QUALITY_GATE_PROFILES",
    "STORY_LOGIC_CODES",
    "QualityGateDimensionBundle",
    "build_quality_gate_dimension_bundle",
    "build_quality_gate_dimensions",
    "citation_claim_safety_dimension",
    "dimension",
    "human_finalization_dimension",
    "normalize_profile",
    "quality_gate_verdict",
    "repair_action_ids",
    "reproducibility_dimension",
    "reviewer_acceptability_dimension",
    "status_for_profile",
    "story_logic_dimension",
    "structure_latex_dimension",
    "tier_codes",
    "tier_status",
]
