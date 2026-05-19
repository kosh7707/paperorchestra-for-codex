# Orchestrator v1-alpha merge bar

Date: 2026-05-19
Branch: `orchestrator-v1-runtime`
Baseline head when drafted: `7ff57aa Carry operator rejection memory across feedback cycles`
Relation to `main` when drafted: `97` commits ahead, `0` behind
Status: **alpha bar defined; not yet final-audited for main merge**

This document defines the smaller, honest bar for integrating the v1 runtime as
an alpha.  It does **not** replace the final v1 manuscript-quality acceptance
ledger.  The current final-quality ledger can remain failed while v1-alpha is
mergeable, provided failures are traceable, public-safe, and never represented
as submission readiness.

## 1. Alpha principle

v1-alpha is acceptable when PaperOrchestra can run its v1 orchestration surfaces
and fail safely/actionably.

Alpha success means:

- entrypoints work;
- deterministic tests pass;
- controlled smoke passes;
- quality failures are caught by gates/artifacts/logs;
- final audit bugs can be traced to concrete evidence;
- private material does not leak into the public repository;
- documentation does not imply submission-ready manuscript quality.

Alpha success does **not** mean:

- the generated manuscript is ready to submit;
- every citation/claim quality gate passes;
- all figures are publication-final;
- operator repair convergence is perfect;
- `pass_loop_verified` equals paper readiness.

## 2. Final-v1 gates that may remain open for alpha

The following current final-quality gates may remain failed/blocked for
v1-alpha if they are visible, documented, and traceable:

- `no_unsupported_critical_claims`
- `citation_integrity`
- `supplied_figures_inventoried_matched_or_blocked`
- `hard_gates_no_fail_except_human_polish`
- `critic_consensus_near_ready_or_better`

These are manuscript-quality or finalization gates.  Alpha may ship with them
open only if the runtime does not hide them as success.

## 3. Alpha hard blockers

Any of the following blocks v1-alpha merge:

1. Git working tree is not clean at merge audit time.
2. Full pytest fails.
3. `scripts/pre-live-check.sh --all` fails.
4. Controlled quality-gate smoke fails in a way that is not documented as an
   explicit known limitation.
5. CLI, MCP, Skill, or orchestrator entrypoints are broken.
6. Mock demo, compile, or export path is broken.
7. Private material, raw prompts, raw private manuscript text, raw BibTeX,
   private source/figure names, or raw `/tmp` evidence leaks into committed
   files.
8. A known quality failure is reported as readiness or success.
9. Final audit discovers a bug but the bug cannot be traced to a command,
   phase, gate, artifact, or redacted report.
10. README/ENVIRONMENT/Skill docs omit the alpha status and known limitations.

## 4. Per-goal verification policy

Fresh full live smoke is **not** the per-goal verifier.

Each remaining Goal A/B/C slice must close through TDD-first deterministic
verification:

- write or update the failing unit/functional/fixture test first;
- implement the minimum behavior;
- run targeted tests;
- run relevant controlled smoke if the slice crosses runtime boundaries;
- get Critic review for non-trivial quality-gate behavior;
- commit/push with evidence.

Fresh full live smoke is reserved for the final integration audit only.

## 5. Final audit contract

Before main integration, run one final audit pass.  At minimum it must include:

```bash
.venv/bin/python -m pytest -q
scripts/pre-live-check.sh --all
```

And it should include a final fresh full live smoke unless explicitly deferred by
the user.  If fresh full live smoke is run, its purpose is integration and
traceability, not proving that every manuscript-quality gate is green.

For every failure found during final audit, record:

- command;
- environment/context;
- session/run id if available;
- phase or gate that caught the problem;
- artifact or redacted report path;
- expected vs actual status;
- fix commit, or explicit known limitation if intentionally deferred.

Use the public-safe ledger surface to validate those records before relying on
them:

```bash
paperorchestra final-audit-ledger --bugs docs/reports/<public-safe-bug-file>.json
paperorchestra final-audit-ledger --bugs docs/reports/<public-safe-bug-file>.json --json
```

The bug file must contain a top-level `bugs` list.  Each bug requires a public
traceable command label, phase, gate, artifact reference, expected status,
actual status, and resolution for fixed/deferred/known-limitation entries.  Do
not store raw prompts, private manuscript text, raw BibTeX, private material
names, or raw `/tmp` paths in this ledger.

## 6. Required alpha evidence bundle

The merge audit should leave a public-safe evidence bundle with:

- full pytest output summary;
- pre-live evidence path;
- controlled smoke evidence path if separate from pre-live;
- MCP smoke result or documented active-session limitation;
- mock/demo/compile/export evidence or pre-live coverage reference;
- private leakage scan result;
- final audit bug ledger validated by `paperorchestra final-audit-ledger`;
- alpha limitations summary;
- post-merge smoke plan.

## 7. Current baseline evidence

At drafting time, the latest completed slice has this evidence:

- `tests/test_pipeline_quality_and_operator_feedback.py -q` -> `131 passed`;
- `tests/test_orchestra_acceptance_ledger.py -q` -> `20 passed, 29 subtests`;
- `tests/test_paperorchestra_skill_guidance.py tests/test_docs_grounding_contracts.py -q`
  -> `14 passed`;
- `.venv/bin/python -m pytest -q` -> `1057 passed, 202 subtests passed`;
- `scripts/pre-live-check.sh --all` -> PASS at
  `review/pre-live-check-20260519T093346Z`;
- Critic re-review -> APPROVE after stale packet-carried execution negative
  test;
- Critic review -> APPROVE for the final-audit bug ledger validator;
- Critic review -> APPROVE for v1-alpha README/ENVIRONMENT/Skill disclosure;
- final fresh full live smoke after this slice -> **not yet run**.

## 8. Merge decision rule

v1-alpha may be merged to `main` only when:

1. all alpha hard blockers are cleared;
2. final-quality open gates are documented as alpha limitations rather than
   hidden readiness;
3. final audit evidence is complete and public-safe;
4. main merge and post-merge smoke plan are recorded.
