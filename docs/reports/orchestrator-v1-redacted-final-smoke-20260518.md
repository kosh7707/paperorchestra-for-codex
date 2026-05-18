# Orchestrator v1 private final-smoke summary (redacted)

Date: 2026-05-18

Branch: `orchestrator-v1-runtime`

Head: `99be941`

Scope: public-safe summary only. Raw evidence, prompts, source paths, source names, manuscript text, BibTeX, PDFs, and provider commands remain outside the repository.

## Result

The private final live smoke completed as a **system-loop pass**, not a submission-readiness claim.

```json
{
  "smoke_verdict": "pass_loop_verified",
  "qa_loop_terminal_verdict": "human_needed",
  "qa_loop_terminal_exit_code": 20,
  "quality_gate_status": "fail_tier2",
  "manuscript_readiness": "not_ready",
  "operator_feedback_cycles": 5,
  "operator_feedback_cycles_attempted": 5,
  "operator_feedback_cycles_promoted": 2,
  "operator_feedback_cycles_rolled_back": 3,
  "operator_feedback_cycles_failed": 0,
  "orchestration_stop_reason": "operator_cycle_cap_reached"
}
```

## Redacted acceptance summary

```json
{
  "overall_status": "pass",
  "smoke_mode": "private_final",
  "checks": {
    "evidence_completeness": "pass",
    "fresh_smoke_verdict": "pass",
    "material_invariance": "pass",
    "meta_leakage_scan": "pass",
    "operator_feedback_cycles": "pass",
    "exported_pdf_tex_evidence": "pass",
    "material_manifest_safety": "pass"
  },
  "redacted_counts": {
    "operator_feedback_cycles": 5,
    "artifact_file_count": 1713,
    "material_file_count": 14
  },
  "acceptance_statuses": {
    "fresh_container_functional_smoke": "blocked",
    "private_final_live_smoke_redacted": "pass",
    "private_leakage_scan": "pass",
    "compile_export": "pass",
    "exported_pdf_tex_evidence_bundle": "pass"
  }
}
```

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
  "citation_support_summary": {
    "supported": 11,
    "needs_manual_check": 12,
    "weakly_supported": 4
  },
  "citation_integrity": {
    "audit_status": "fail",
    "audit_failing_codes": [
      "citation_duplicate_support"
    ],
    "critic_status": "fail",
    "critic_failing_codes": [
      "citation_duplicate_support",
      "citation_integrity_audit_fail"
    ]
  },
  "rendered_reference_audit": {
    "status": "pass",
    "bib_entry_count": 17,
    "cited_key_count": 14,
    "visible_reference_count": 14,
    "missing_bib_keys_for_cites": [],
    "unknown_metadata_keys": [],
    "failing_codes": []
  },
  "figure_review_summary": {
    "figure_count": 3,
    "warning_count": 2,
    "warning_codes": [
      "wide_figure_mismatch"
    ]
  }
}
```

Interpretation: the runtime, evidence bundle, material-invariance, leakage, operator-cycle, compile/export, and redacted summary gates passed. The manuscript remains `not_ready` because Tier 2 claim/citation safety still fails: citation support has weak/manual-check items and citation integrity reports duplicate-support failures. Figure placement was reviewed but still has non-fatal warnings.

## Public evidence handling

- Raw evidence location is redacted and local-only.
- The committed machine summary records only status/count/hash fields.
- The transient redacted acceptance artifact was parsed and verified locally; raw paths and raw artifact content are not committed.
