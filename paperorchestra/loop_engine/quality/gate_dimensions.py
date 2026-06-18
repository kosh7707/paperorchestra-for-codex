from __future__ import annotations

from dataclasses import dataclass
from typing import Any

QUALITY_GATE_PROFILES = {"auto", "mock", "ralph", "claim_safe"}
STORY_LOGIC_CODES = {
    "planning_satisfaction_missing",
    "planning_satisfaction_stale",
    "planning_satisfaction_failed",
    "narrative_plan_missing",
    "claim_map_missing",
    "citation_placement_plan_missing",
    "expected_section_missing",
    "expected_section_too_shallow",
}


@dataclass(frozen=True)
class QualityGateDimensionBundle:
    resolved_profile: str
    dimensions: dict[str, dict[str, Any]]
    blocked_dimensions: list[str]
    warning_dimensions: list[str]
    verdict: str


def normalize_profile(profile: str | None, quality_eval: dict[str, Any]) -> str:
    requested = (profile or "auto").strip().lower().replace("-", "_")
    if requested not in QUALITY_GATE_PROFILES:
        raise ValueError(f"Unknown quality-gate profile {profile!r}; expected one of: {', '.join(sorted(QUALITY_GATE_PROFILES))}")
    if requested != "auto":
        return requested
    mode = str(quality_eval.get("mode") or "").strip().lower()
    provenance = quality_eval.get("provenance_trust") if isinstance(quality_eval.get("provenance_trust"), dict) else {}
    if provenance.get("level") == "mock":
        return "mock"
    if mode == "claim_safe":
        return "claim_safe"
    return "ralph"


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


def build_quality_gate_dimensions(
    quality_eval: dict[str, Any],
    plan: dict[str, Any],
    *,
    profile: str,
) -> dict[str, dict[str, Any]]:
    tiers = quality_eval.get("tiers") if isinstance(quality_eval.get("tiers"), dict) else {}
    dimensions: dict[str, dict[str, Any]] = {}
    dimensions["structure_latex"] = structure_latex_dimension(quality_eval, plan, profile=profile)
    dimensions["citation_claim_safety"] = citation_claim_safety_dimension(quality_eval, plan, profile=profile)
    dimensions["story_logic"] = story_logic_dimension(quality_eval, plan, profile=profile)
    dimensions["reviewer_acceptability"] = reviewer_acceptability_dimension(quality_eval, plan, tiers=tiers, profile=profile)
    dimensions["reproducibility"] = reproducibility_dimension(quality_eval, plan, profile=profile)
    dimensions["human_finalization"] = human_finalization_dimension(tiers)
    return dimensions


def structure_latex_dimension(quality_eval: dict[str, Any], plan: dict[str, Any], *, profile: str) -> dict[str, Any]:
    non_reviewable = quality_eval.get("non_reviewable") if isinstance(quality_eval.get("non_reviewable"), dict) else {}
    tier0_status = tier_status(quality_eval, "tier_0_preconditions")
    tier1_status = tier_status(quality_eval, "tier_1_structural")
    structural_codes = tier_codes(quality_eval, "tier_0_preconditions") + tier_codes(quality_eval, "tier_1_structural")
    structural_codes += [str(code) for code in (non_reviewable.get("failing_codes") or []) if code]
    structural_raw = "fail" if structural_codes or tier0_status == "fail" or tier1_status == "fail" else "pass"
    structural_status, structural_blocking = status_for_profile(structural_raw, profile=profile, axis="structure_latex")
    return dimension(
        name="LaTeX, structure, artifact freshness",
        status=structural_status,
        blocking=structural_blocking,
        failing_codes=structural_codes,
        sources=["tier_0_preconditions", "tier_1_structural", "non_reviewable"],
        details={
            "tier_0_status": tier0_status,
            "tier_1_status": tier1_status,
            "non_reviewable_status": non_reviewable.get("status"),
            "repair_action_ids": repair_action_ids(plan, set(structural_codes)),
        },
    )


def citation_claim_safety_dimension(quality_eval: dict[str, Any], plan: dict[str, Any], *, profile: str) -> dict[str, Any]:
    tier2_status = tier_status(quality_eval, "tier_2_claim_safety")
    claim_codes = tier_codes(quality_eval, "tier_2_claim_safety")
    claim_status, claim_blocking = status_for_profile(tier2_status, profile=profile, axis="citation_claim_safety")
    return dimension(
        name="Citation fidelity and claim safety",
        status=claim_status,
        blocking=claim_blocking,
        failing_codes=claim_codes,
        sources=["tier_2_claim_safety"],
        details={"repair_action_ids": repair_action_ids(plan, set(claim_codes))},
    )


def story_logic_dimension(quality_eval: dict[str, Any], plan: dict[str, Any], *, profile: str) -> dict[str, Any]:
    tier2_status = tier_status(quality_eval, "tier_2_claim_safety")
    claim_codes = tier_codes(quality_eval, "tier_2_claim_safety")
    story_codes = [code for code in claim_codes if code in STORY_LOGIC_CODES]
    story_raw = "fail" if story_codes else ("warn" if tier2_status.startswith("skipped") else "pass")
    story_status, story_blocking = status_for_profile(story_raw, profile=profile, axis="story_logic")
    return dimension(
        name="Narrative logic, positioning, and section story",
        status=story_status,
        blocking=story_blocking,
        failing_codes=story_codes,
        sources=["planning_artifacts", "tier_2_claim_safety"],
        details={"repair_action_ids": repair_action_ids(plan, set(story_codes))},
    )


def reviewer_acceptability_dimension(
    quality_eval: dict[str, Any],
    plan: dict[str, Any],
    *,
    tiers: dict[str, Any],
    profile: str,
) -> dict[str, Any]:
    tier3_status = tier_status(quality_eval, "tier_3_scholarly_quality")
    tier3_codes = tier_codes(quality_eval, "tier_3_scholarly_quality")
    reviewer_status, reviewer_blocking = status_for_profile(tier3_status, profile=profile, axis="reviewer_acceptability")
    tier3 = tiers.get("tier_3_scholarly_quality") if isinstance(tiers.get("tier_3_scholarly_quality"), dict) else {}
    return dimension(
        name="Reviewer acceptability and scholarly quality",
        status=reviewer_status,
        blocking=reviewer_blocking,
        failing_codes=tier3_codes,
        sources=["tier_3_scholarly_quality", "review.latest.json", "section_review"],
        details={
            "overall_score": tier3.get("overall_score"),
            "axis_scores": tier3.get("axis_scores"),
            "anti_inflation_triggered": bool(tier3.get("anti_inflation_triggered")),
            "repair_action_ids": repair_action_ids(plan, set(tier3_codes)),
        },
    )


def reproducibility_dimension(quality_eval: dict[str, Any], plan: dict[str, Any], *, profile: str) -> dict[str, Any]:
    provenance = quality_eval.get("provenance_trust") if isinstance(quality_eval.get("provenance_trust"), dict) else {}
    repro_snapshot = plan.get("audit_snapshots", {}).get("reproducibility") if isinstance(plan.get("audit_snapshots"), dict) else {}
    fidelity_snapshot = plan.get("audit_snapshots", {}).get("fidelity") if isinstance(plan.get("audit_snapshots"), dict) else {}
    repro_codes: list[str] = []
    provenance_level = str(provenance.get("level") or "unknown")
    if profile == "claim_safe" and provenance_level != "live":
        repro_codes.append(f"provenance_not_live:{provenance_level}")
    if isinstance(repro_snapshot, dict) and repro_snapshot.get("verdict") == "BLOCK":
        repro_codes.append("reproducibility_block")
    if isinstance(fidelity_snapshot, dict) and str(fidelity_snapshot.get("overall_status") or "") == "fail":
        repro_codes.append("fidelity_fail")
    repro_raw = "fail" if repro_codes else ("warn" if provenance_level in {"mock", "mixed", "unknown"} else "pass")
    repro_status, repro_blocking = status_for_profile(repro_raw, profile=profile, axis="reproducibility")
    return dimension(
        name="Experiment, method, provenance, and reproducibility evidence",
        status=repro_status,
        blocking=repro_blocking,
        failing_codes=repro_codes,
        sources=["reproducibility_audit", "fidelity_audit", "provenance_trust"],
        details={
            "provenance_level": provenance_level,
            "reproducibility_verdict": repro_snapshot.get("verdict") if isinstance(repro_snapshot, dict) else None,
            "fidelity_status": fidelity_snapshot.get("overall_status") if isinstance(fidelity_snapshot, dict) else None,
        },
    )


def human_finalization_dimension(tiers: dict[str, Any]) -> dict[str, Any]:
    tier4 = tiers.get("tier_4_human_finalization") if isinstance(tiers.get("tier_4_human_finalization"), dict) else {}
    return dimension(
        name="Human-owned final proof, bibliography curation, venue fit, and submission decision",
        status="human_owned",
        blocking=False,
        failing_codes=[],
        sources=["tier_4_human_finalization"],
        details={"outstanding_owners": tier4.get("outstanding_owners", [])},
    )


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


def status_for_profile(raw_status: str, *, profile: str, axis: str) -> tuple[str, bool]:
    if raw_status in {"pass", "never_automated"}:
        return ("pass" if raw_status == "pass" else "human_owned", False)
    if raw_status.startswith("skipped"):
        return ("block" if profile == "claim_safe" else "warn", profile == "claim_safe")
    if raw_status == "fail":
        if profile == "mock" and axis in {"story_logic", "citation_claim_safety", "reviewer_acceptability", "reproducibility"}:
            return "warn", False
        return "block", True
    if raw_status == "warn":
        return ("block", True) if profile == "claim_safe" else ("warn", False)
    return ("warn", False) if profile == "mock" else ("block", True)


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
