# Slice AH private final-smoke summary (redacted)

Date: 2026-05-14

Branch: `orchestrator-v1-runtime`

Final tested head: `aebf96e`

## Scope

This report records only public-safe evidence for the private final-smoke run.
It intentionally omits private material names, raw paths, prompts, responses,
generated manuscript text, generated BibTeX, generated PDFs, and provider
commands.

## Result

The fresh full live smoke loop completed with:

```text
smoke_verdict: pass_loop_verified
qa_loop_final_verdict: human_needed
stop_reason: operator_cycle_cap_reached
operator_feedback_cycles: 5
operator_feedback_cycles_promoted: 4
operator_feedback_cycles_rolled_back: 1
operator_feedback_cycles_failed: 0
manuscript_readiness: not_ready
quality_gate_status: fail_tier2
```

Interpretation: this is a **system-loop pass**, not a submission-readiness
claim. The run proved that the fresh-container live loop can run through
preflight, live provider calls, compile, critique, five bounded operator cycles,
final gates, evidence validation, and redacted summarization. The generated
paper still requires human/author work before submission.

## Redacted acceptance summary

`paperorchestra summarize-fresh-smoke --smoke-mode private_final` returned:

```json
{
  "schema_version": "fresh-smoke-acceptance-summary/1",
  "smoke_mode": "private_final",
  "overall_status": "pass",
  "checks": {
    "evidence_completeness": "pass",
    "fresh_smoke_verdict": "pass",
    "material_invariance": "pass",
    "meta_leakage_scan": "pass",
    "operator_feedback_cycles": "pass",
    "exported_pdf_tex_evidence": "pass",
    "material_manifest_safety": "pass"
  },
  "acceptance": {
    "fresh_container_functional_smoke": "blocked",
    "private_final_live_smoke_redacted": "pass",
    "private_leakage_scan": "pass",
    "compile_export": "pass",
    "exported_pdf_tex_evidence_bundle": "pass"
  },
  "redacted_counts": {
    "operator_feedback_cycles": 5,
    "artifact_file_count": 1617,
    "material_file_count": 14
  }
}
```

`fresh_container_functional_smoke` is blocked by design because this summary is
private-final evidence, not the synthetic-container proof mode.

## Quality tiers at terminal state

```json
{
  "tier_0_preconditions": "pass",
  "tier_1_structural": "pass",
  "tier_2_claim_safety": "fail",
  "tier_3_scholarly_quality": "skipped_due_to_upstream_fail",
  "tier_4_human_finalization": "never_automated"
}
```

This confirms the loop did not overclaim manuscript quality. It stopped at the
operator-cycle cap with `human_needed`.

## Release-safety handling

The raw evidence root is private QA evidence, so private/domain residue was
allowed for the raw evidence scan while secrets remained blocking:

```json
{
  "status": "pass",
  "allow_private_residue": true,
  "finding_count": 35265,
  "allowed_private_residue_count": 35265,
  "blocking_finding_count": 0
}
```

The committed redacted summary files were separately scanned with the private
denylist:

```text
status: ok
scan_mode: explicit_paths
scanned_file_count: 2
match_count: 0
```

## Fixes discovered during AH

The run forced three generic fixes before the final pass:

1. Redacted prep-manifest compatibility:
   `file_count` / `files` are now accepted by the public-safe final-smoke
   summarizer.
2. Public evidence metadata redaction:
   wrapper-generated README/contract/command metadata no longer stores raw
   private paths or raw provider argv/prefix.
3. Section claim repair:
   `write_sections` now performs one validator-guided repair for required-claim
   and narrative-role coverage failures, while still rejecting invalid repaired
   drafts.

## Verification

Before the final smoke pass, local verification included:

```text
pytest -q: 980 passed, 182 subtests passed
scripts/pre-live-check.sh --all: PASS
private leakage denylist scan over tracked files: match_count 0
tracked private-domain literal grep: no matches
git diff --check: clean
```
