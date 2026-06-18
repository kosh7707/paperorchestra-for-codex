from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.loop_engine.quality.artifact_checks import _figure_grounding_check
from paperorchestra.loop_engine.quality.citation_support import _citation_support_check
from paperorchestra.loop_engine.quality.eval_tiers import _status_from_failures, _tier
from paperorchestra.loop_engine.quality.policy import TIER2_CLAIM_CODES
from paperorchestra.loop_engine.quality.reviews import _validation_issue_counts
from paperorchestra.loop_engine.quality.source_checks import (
    _high_risk_claim_sweep,
    _planning_satisfaction_check,
    _source_material_fidelity_check,
)
from paperorchestra.manuscript.source_obligations import evaluate_source_obligations
from paperorchestra.reviews.citation_integrity import citation_integrity_check
from paperorchestra.reviews.citation_quality import build_citation_quality_gate_internal


def build_claim_safety_tier(
    *,
    cwd: str | Path | None,
    state,
    mode: str,
    reproducibility: dict[str, Any],
    planning_status: dict[str, Any],
    ralph_evidence: dict[str, Any],
) -> dict[str, Any]:
    claim_counts = _validation_issue_counts(reproducibility)
    citation_support = _citation_support_check(cwd, state, quality_mode=mode)
    citation_integrity = citation_integrity_check(cwd, state, quality_mode=mode)
    citation_quality = build_citation_quality_gate_internal(cwd, quality_mode=mode)
    source_material = _source_material_fidelity_check(state)
    figure_grounding = _figure_grounding_check(state)
    source_obligations = evaluate_source_obligations(cwd)
    high_risk_claims = _high_risk_claim_sweep(state, source_obligations)
    planning_satisfaction = _planning_satisfaction_check(state, planning_status)
    tier2_failing: list[str] = []
    for code in sorted(TIER2_CLAIM_CODES):
        if claim_counts.get(code, 0) > 0:
            tier2_failing.append(code)
    tier2_failing.extend(citation_support.get("failing_codes") or [])
    tier2_failing.extend(citation_integrity.get("failing_codes") or [])
    tier2_failing.extend(citation_quality.get("hard_gate_failures") or [])
    tier2_failing.extend(figure_grounding.get("failing_codes") or [])
    tier2_failing.extend(ralph_evidence.get("failing_codes") or [])
    tier2_failing.extend(source_material.get("failing_codes") or [])
    tier2_failing.extend(source_obligations.get("failing_codes") or [])
    tier2_failing.extend(high_risk_claims.get("failing_codes") or [])
    tier2_failing.extend(planning_satisfaction.get("failing_codes") or [])
    tier2_warn_only = mode == "draft"
    if tier2_warn_only and tier2_failing:
        mode_effect = "warning_in_draft"
    elif tier2_failing:
        mode_effect = "hard_fail_in_claim_safe"
    else:
        mode_effect = "pass"
    return _tier(
        status=_status_from_failures(tier2_failing, warn_only=tier2_warn_only),
        checks={
            "unsupported_comparative_claims": {
                "status": "fail" if claim_counts.get("unsupported_comparative_claim", 0) else "pass",
                "count": claim_counts.get("unsupported_comparative_claim", 0),
            },
            "numeric_grounding": {
                "status": "fail" if claim_counts.get("numeric_grounding_mismatch", 0) else "pass",
                "count": claim_counts.get("numeric_grounding_mismatch", 0),
            },
            "citation_support_critic": citation_support,
            "citation_integrity_gate": citation_integrity,
            "citation_quality_gate": citation_quality,
            "figure_grounding": figure_grounding,
            "ralph_evidence": ralph_evidence,
            "source_material_fidelity": source_material,
            "source_obligations": source_obligations,
            "high_risk_claim_sweep": high_risk_claims,
            "planning_satisfaction": planning_satisfaction,
            "experiment_log_consistency": {"status": "not_automated", "owner": "human_or_domain_critic"},
        },
        failing_codes=tier2_failing,
        mode_effect=mode_effect,
    )
