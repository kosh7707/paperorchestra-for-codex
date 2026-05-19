# Orchestrator v1 private final-smoke summary (redacted)

Date: 2026-05-19

Branch: `orchestrator-v1-runtime`

Head: `3c173d4`

Scope: public-safe summary only. Raw evidence, prompts, source paths, source names, manuscript text, BibTeX, PDFs, and provider commands remain outside the repository.

## Result

The private final live smoke completed as a **system-loop pass**, not a submission-readiness claim.

```json
{
  "schema_version": "fresh-smoke-verdict/1",
  "smoke_verdict": "pass_loop_verified",
  "qa_loop_terminal_verdict": "human_needed",
  "qa_loop_terminal_exit_code": 20,
  "first_failing_predicate": null,
  "first_failing_artifact": null,
  "operator_feedback_cycles": 5,
  "operator_feedback_cycles_attempted": 5,
  "operator_feedback_cycles_promoted": 0,
  "operator_feedback_cycles_rolled_back": 5,
  "operator_feedback_cycles_failed": 0,
  "material_invariance_status": "pass",
  "evidence_completeness_status": "pass",
  "lane_a_status": "pass",
  "critic_verdict": "pass",
  "quality_gate_status": "fail_tier2",
  "manuscript_readiness": "not_ready",
  "orchestration_stop_reason": "operator_cycle_cap_reached"
}
```

## What this run newly proves

- The fresh-container pre-live gate now tests the current checkout instead of a stale editable install.
- The active Tier-2 metric-regression promotion guard is effective in the full smoke: all 5 operator-feedback candidates were rolled back, and none were promoted while regressing still-active Tier-2 metrics.
- Evidence completeness, material invariance, Lane-A predicates, meta-leakage scan, and the terminal Critic check all passed.

## Quality and remaining blockers

```json
{
  "quality_tiers": {
    "tier_0_preconditions": "pass",
    "tier_1_structural": "pass",
    "tier_2_claim_safety": "fail",
    "tier_3_scholarly_quality": "skipped_due_to_upstream_fail",
    "tier_4_human_finalization": "never_automated"
  },
  "tier2_failing_codes": [
    "citation_bomb_detected",
    "citation_critic_failed",
    "citation_duplicate_support",
    "citation_integrity_audit_fail",
    "citation_integrity_failed",
    "citation_source_match_fail",
    "citation_support_manual_check",
    "citation_support_unsupported",
    "citation_support_weak",
    "claim_source_mismatch",
    "critical_unsupported_citation",
    "high_risk_uncited_claim"
  ],
  "citation_support_summary": {
    "weakly_supported": 4,
    "supported": 9,
    "needs_manual_check": 3,
    "unsupported": 1
  },
  "citation_quality_counts": {
    "critical_need_count": 8,
    "critical_unknown_reference_count": 0,
    "critical_unsupported_count": 1,
    "citation_bomb_count": 3,
    "duplicate_reference_count": 1
  },
  "high_risk_claim_sweep": {
    "status": "fail",
    "item_count": 41
  }
}
```

Interpretation: this is a safer failure than the previous smoke. The system correctly refused candidate repairs that improved some citation conditions while worsening active manual/high-risk metrics. The manuscript therefore remains `not_ready` and the next generic hardening target is repair convergence: future feedback cycles should carry rejection memory or otherwise avoid repeating the same non-promotable repair shape.

## Operator-feedback digest

```json
[
  {
    "cycle": 1,
    "promotion_status": "rolled_back",
    "gate_reasons": [
      "active_tier2_metric_regression"
    ],
    "resolved_active_failure_count": 9,
    "new_tier2_failure_count": 0,
    "metric_regression_count": 2,
    "metric_improvement_count": 5,
    "base_total": 54,
    "candidate_total": 50
  },
  {
    "cycle": 2,
    "promotion_status": "rolled_back",
    "gate_reasons": [
      "active_tier2_metric_regression"
    ],
    "resolved_active_failure_count": 9,
    "new_tier2_failure_count": 0,
    "metric_regression_count": 2,
    "metric_improvement_count": 5,
    "base_total": 54,
    "candidate_total": 50
  },
  {
    "cycle": 3,
    "promotion_status": "rolled_back",
    "gate_reasons": [
      "active_tier2_metric_regression"
    ],
    "resolved_active_failure_count": 9,
    "new_tier2_failure_count": 0,
    "metric_regression_count": 2,
    "metric_improvement_count": 5,
    "base_total": 54,
    "candidate_total": 50
  },
  {
    "cycle": 4,
    "promotion_status": "rolled_back",
    "gate_reasons": [
      "active_tier2_metric_regression"
    ],
    "resolved_active_failure_count": 9,
    "new_tier2_failure_count": 0,
    "metric_regression_count": 2,
    "metric_improvement_count": 5,
    "base_total": 54,
    "candidate_total": 50
  },
  {
    "cycle": 5,
    "promotion_status": "rolled_back",
    "gate_reasons": [
      "active_tier2_metric_regression"
    ],
    "resolved_active_failure_count": 9,
    "new_tier2_failure_count": 0,
    "metric_regression_count": 2,
    "metric_improvement_count": 5,
    "base_total": 54,
    "candidate_total": 50
  }
]
```

## Redacted acceptance checks

```json
{
  "lane_a": "pass",
  "evidence_completeness": "pass",
  "meta_leakage": "pass",
  "release_safety_final": "pass"
}
```

## Public evidence handling

- Raw evidence location is redacted and local-only.
- The committed machine summary records only status/count/code fields.
- No private material names, raw private paths, manuscript text, or bibliography content are committed.
