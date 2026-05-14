# Orchestrator v1 Tier-2 Quality Triage Plan

Status: active triage plan  
Scope: generic PaperOrchestra quality-loop hardening, not a domain-specific paper
adapter.

## 1. Why this plan exists

A fresh full live smoke can exercise the full loop while still ending in
`human_needed` / `not_ready`. That is a valid system outcome, but it must be
actionable. The current Tier-2 blockers split into four generic families:

1. missing or stale session evidence for manually orchestrated fresh-smoke runs;
2. provenance semantics for cited references that are not all live search papers;
3. citation-density / duplicate-support / high-risk-claim repair effectiveness;
4. residual citation-support cases that need either machine repair or true author
   ownership.

This plan keeps those concerns separate. Passing a smoke harness is not the same
as manuscript readiness, and no slice may weaken a validator only to make a
smoke pass.

## 2. Non-goals

- Do not encode private material names, benchmark names, paper titles, or
  domain-specific terms in public code or tests.
- Do not treat private raw evidence as a public release artifact.
- Do not mark mixed or curated provenance as live search provenance.
- Do not mark runtime parity implemented when a required lane was not actually
  recorded.
- Do not upgrade citation support without web evidence, claim softening, claim
  deletion, or explicit author/operator ownership.

## 3. Slice T2-A — manually orchestrated session-evidence freshness

### Goal

Fresh full live smoke uses explicit CLI stages rather than the monolithic
`paperorchestra run` pipeline. It must still record the same session evidence
that downstream quality gates consume.

### Required behavior

- A current compile-environment report is recorded in the session before quality
  snapshots that may produce `fidelity_compile_environment_ready_missing`.
- A runtime-parity report can be recorded from the session's lane manifests and
  stored in `state.artifacts.latest_runtime_parity_json`.
- Runtime parity is not forced to pass. If the manual smoke path lacks a lane
  that the parity contract requires, the report must remain partial with a
  precise reason.
- Quality-loop planning should stop emitting compile-env/runtime-parity missing
  actions when the current evidence artifacts exist and are current.

### Tests before implementation

1. A CLI/helper test records runtime parity from synthetic lane manifests and
   updates `latest_runtime_parity_json`.
2. A wrapper-order test proves `check-compile-env` runs before the first and
   final claim-safe `quality-eval`.
3. A wrapper-order test proves runtime-parity recording runs before the first and
   final claim-safe `quality-eval`.
4. A quality-loop plan fixture with implemented compile-environment evidence and
   an existing runtime-parity artifact does not emit
   `fidelity_compile_environment_ready_missing` or
   `fidelity_runtime_parity_missing`.

### Acceptance criteria

- Targeted tests pass.
- Full test suite passes.
- `scripts/pre-live-check.sh --all` passes when wrapper behavior changes.
- Public leakage scan reports zero matches.

## 4. Slice T2-B — cited-reference provenance semantics

### Goal

Claim-safe live verification should evaluate the provenance of cited references
accurately. It should not count unused registry residue as a manuscript blocker,
and it should not conflate authoritative mixed provenance with live search
verification.

### Required behavior

- Cited live-search entries remain accepted as live provenance.
- Cited curated-only entries remain blocking when strict live provenance is
  required.
- Cited authoritative web/source entries may be classified as mixed provenance,
  but only an explicit acceptance path may allow them to pass a claim-safe gate.
- Unused registry entries do not block if they are not cited by the current
  manuscript.

### Tests before implementation

1. A registry with only live-search cited entries passes strict live provenance.
2. A registry with cited curated-only entries fails strict live provenance.
3. A registry with cited authoritative mixed-provenance entries yields a distinct
   mixed-provenance state, not a false live-search state.
4. Unused curated registry entries do not block when all cited entries have
   acceptable provenance.

## 5. Slice T2-C — citation-density and high-risk-claim repair effectiveness

### Goal

Semi-automatic repair must reduce the failing condition it is asked to repair.
It may not pass by adding unsupported bibliography keys or weakening the audit.

### Required behavior

- Citation-density issues are included in the repair prompt as structured
  issue-context.
- High-risk uncited claims are included in the repair prompt as structured
  issue-context.
- Candidate repairs are checked by the same citation-integrity and high-risk
  sweep that failed the original manuscript.
- Unknown or newly invented citation keys still reject the candidate.

### Tests before implementation

1. A deterministic fake-provider fixture sees citation-density and high-risk
   issue-context in the prompt.
2. A candidate that splits/removes redundant citation clusters passes the
   citation-integrity audit when the original fails.
3. A candidate that scopes, cites with existing keys, or deletes high-risk
   uncited claims passes the high-risk sweep when the original fails.
4. A candidate with a new citation key is rejected.

## 6. Slice T2-D — residual citation-support manual-check policy

### Goal

`citation_support_manual_check` should be reserved for cases that truly need
author/operator judgment. Machine-solvable cases should route to a bounded
semi-automatic candidate repair.

### Required behavior

- Manual-check items with concrete suggested fixes and existing citation evidence
  can route to semi-automatic repair.
- Manual-check items that require author-domain interpretation remain
  `human_needed`.
- No item may be upgraded to supported without web evidence, claim softening,
  claim deletion, or explicit author/operator ownership.

### Tests before implementation

1. Machine-solvable manual-check fixtures route to semi-auto repair.
2. Author-judgment fixtures remain `human_needed`.
3. Unsupported support statuses cannot be upgraded by metadata-only evidence.

## 7. Verification loop per slice

Every implementation slice follows:

1. mini-plan;
2. Critic plan validation;
3. red tests;
4. implementation;
5. targeted tests;
6. full tests when code changes;
7. pre-live check when wrapper/quality behavior changes;
8. public leakage scan;
9. Critic implementation validation;
10. Lore commit and push.

After T2-A through T2-D have enough evidence, rerun fresh full live smoke from a
fresh container with private raw-evidence residue explicitly allowed. The
success criterion is not merely script exit code: the run must either reach
`ready_for_human_finalization` or fail with a smaller set of truly human-owned,
actionable blockers.
