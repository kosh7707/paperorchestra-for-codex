# Orchestrator v1 remaining work handoff

Date: 2026-05-19
Branch: `orchestrator-v1-runtime`
Head at handoff: `4f65924 Prevent repeated operator repair dead ends`
Relation to `main`: `96` commits ahead at handoff
Status: **not merge-ready / not goal-complete**

This document is the single routing point for resuming the work later. It intentionally summarizes private-smoke outcomes using public-safe generic codes/counts only. Do not add private manuscript text, private material names, raw BibTeX, raw prompts, or raw `/tmp` evidence contents to this file.

## 1. Current strategic decision

The user does **not** want selective cherry-pick integration into `main`.

If this branch is merged, the intended direction is:

> merge the full v1 branch into `main` only when the v1 branch is genuinely main-ready.

Therefore the remaining work is not “pick a few safe commits.” The remaining work is to finish the v1 branch until its acceptance gates are satisfied, then perform a full merge-readiness audit.

## 2. Current local working tree

At handoff there are uncommitted changes:

- `paperorchestra/operator_feedback.py`
- `tests/test_pipeline_quality_and_operator_feedback.py`

These changes are part of the **Repair/Convergence quality** goal, specifically cross-cycle operator-feedback rejection memory.

Last committed/pushed commit:

- `4f65924 Prevent repeated operator repair dead ends`

That committed slice added in-call rejection memory for repeated operator repair attempts. The current uncommitted slice extends this idea across separate operator cycles by reading previous `operator_feedback_execution` evidence from the next operator packet.

Before any merge/audit, decide one of:

1. finish, test, Critic-review, commit, and push the uncommitted cross-cycle memory slice; or
2. stash/drop it and explicitly exclude it from the next audit.

Do **not** judge merge readiness while these changes remain uncommitted.

## 3. The remaining product-quality goals

Ignoring process-only tasks such as final merge mechanics, ledger refresh, or commit cleanup, the remaining PaperOrchestra quality work is best understood as three goals.

### Goal A — Claim/Evidence/Citation quality

Core question:

> Does the manuscript say things that are properly supported by source material and citations?

Current status: **not complete**.

Known failing families from final-smoke evidence include generic Tier-2 claim/citation safety failures such as:

- unsupported or weakly supported critical claims;
- manual-check citation support;
- claim/source mismatch;
- high-risk uncited claims;
- citation bombs;
- duplicate citation support;
- citation integrity failures.

The branch has improved metadata/reference handling, but the remaining problem is deeper than BibTeX existence. The engine must judge whether each citation actually supports the claim where it appears.

Required next work:

1. Re-summarize latest final-smoke Tier-2 failing codes from current evidence.
2. Classify each blocker as machine-solvable vs true author judgment.
3. For machine-solvable blockers, route to targeted repair or evidence refresh before `human_needed`.
4. Ensure critical unsupported claims become either:
   - supported by directly relevant evidence;
   - scoped/deleted; or
   - explicitly author-owned with a hard blocker, not hidden as polish.

Acceptance direction:

- No unsupported critical claim remains; or
- every remaining critical conflict is explicitly author-owned and blocks readiness honestly.

### Goal B — Repair/Convergence quality

Core question:

> When PaperOrchestra finds quality failures, does it actually converge toward a better manuscript instead of repeatedly rolling back bad repairs?

Current status: **active current work**.

Latest committed state:

- `4f65924` prevents repeated operator repair dead ends inside one `apply_operator_feedback` call.

Why that was insufficient:

- Docker full smoke runs separate operator cycles.
- Each cycle has its own `apply_operator_feedback` call.
- The previous cycle's failed attempt must be carried through the next cycle's packet via `operator_feedback_execution`.

Current uncommitted work:

- Extract prior failed attempts from packet-carried `operator_feedback_execution`.
- Feed compact code/count/hash-only `prior_rejected_attempts` into the next refiner review payload.
- Detect repeated failed candidate SHA across cycles and mark it `repeated_non_promotable_candidate`.

Already started tests:

- cross-cycle packet-carried prior rejection memory;
- repeated candidate SHA rejection;
- no candidate approval for repeated non-promotable attempts.

Immediate next commands when resuming:

```bash
git status --short --branch
.venv/bin/python -m pytest tests/test_pipeline_quality_and_operator_feedback.py -k 'packet_carried_prior_rejection_memory or second_attempt_receives_rejection_memory or prior_rejection_memory or repeated_non_promotable_reason' -q
.venv/bin/python -m pytest tests/test_pipeline_quality_and_operator_feedback.py -q
.venv/bin/python -m py_compile paperorchestra/operator_feedback.py tests/test_pipeline_quality_and_operator_feedback.py
git diff --check
```

Then request Critic implementation review before committing.

Acceptance direction:

- Operator cycles must not blindly repeat the same non-promotable repair shape.
- Previous rollback reasons must influence later repair prompts.
- Candidate promotion gates must remain strict; do **not** weaken Tier-2 gates just to pass smoke.
- A failed repair should either converge to a non-regressing candidate or stop with a more actionable blocker.

### Goal C — Figure/Artifact/Finalization quality

Core question:

> Can a human author actually pick up the output, figures, PDF, TeX, and evidence bundle and continue toward submission?

Current status: **blocked/partial**.

Known issue:

- supplied figures are inventoried, but final figure matching/replacement/finalization remains warning-bearing.

Required next work:

1. Verify supplied figure inventory against manuscript figure placeholders.
2. Replace generated placeholders with supplied figures only where semantically safe.
3. For ambiguous figures, emit explicit human-finalization blockers.
4. Ensure export bundles include the right TeX/PDF/evidence artifacts without private leakage.

Acceptance direction:

- Figures are either matched/replaced safely, or explicitly listed as human-finalization blockers.
- No placeholder figure is silently treated as complete.
- Exported PDF/TeX/evidence is human-usable.

## 4. Current acceptance gate status

The acceptance ledger currently says:

- overall: `failed`
- gates: `19`
- pass: `13`
- fail: `4`
- blocked: `1`
- unknown: `1`

Open gates at the latest checked ledger state:

1. `no_unsupported_critical_claims` — fail
2. `citation_integrity` — fail
3. `supplied_figures_inventoried_matched_or_blocked` — blocked
4. `hard_gates_no_fail_except_human_polish` — fail
5. `critic_consensus_near_ready_or_better` — fail
6. `readme_environment_skill_docs_updated` — unknown

Important: the ledger must be refreshed against the latest committed HEAD before final merge decisions. Some entries reference historical smoke evidence and should not be treated as current proof without revalidation.

Canonical files:

- `docs/reports/orchestrator-v1-current-acceptance-ledger.md`
- `docs/reports/orchestrator-v1-current-acceptance-ledger.json`
- `docs/reports/orchestrator-v1-current-acceptance-evidence.json`
- `docs/reports/orchestrator-v1-execution-index.md`
- `docs/architecture/orchestrator-v1-runtime-plan.md`

## 5. Current smoke/evidence interpretation

Latest committed public-safe smoke report files include:

- `docs/reports/orchestrator-v1-redacted-final-smoke-20260519.md`
- `docs/reports/orchestrator-v1-redacted-final-smoke-20260519.summary.json`

Key interpretation:

- system loop: passed;
- material invariance: passed in the later correct-material-root Docker run;
- evidence completeness: passed;
- Lane-A: passed;
- Critic smoke verdict: passed;
- manuscript readiness: `not_ready`;
- quality gate: `fail_tier2`;
- operator cycles: reached cap with rollbacks.

Do not report this as v1 readiness. It is evidence that the runtime can execute and fail safely, not that the manuscript quality gates are satisfied.

A later Docker run after `4f65924` also showed the cross-cycle memory gap: separate operator cycles need prior failure memory from packet-carried `operator_feedback_execution` artifacts. That is the current uncommitted work.

## 6. Verification strategy update: TDD first, live smoke last

The user clarified the intended verification contract after this handoff was
first drafted:

> Each feature slice must be unit/functional/fixture-testable through TDD.
> Fresh full live smoke must be reserved for the final integration audit and
> must not be used as a substitute for per-feature verification.

Therefore the three remaining product goals should **not** each run a fresh
full live smoke loop.  Per-goal closure should use deterministic tests and
bounded controlled smoke only:

- Goal A — claim/evidence/citation quality: fixture-based claim graph,
  citation support, citation-bomb, duplicate-support, and evidence-relevance
  tests.
- Goal B — repair/convergence quality: operator-feedback unit tests,
  rollback/promotion tests, rejection-memory tests, cycle-cap tests, and
  controlled quality-gate smoke.
- Goal C — figure/artifact/finalization quality: supplied-figure inventory,
  placeholder replacement, missing-figure blocker, compile/export, and bundle
  completeness tests.

Fresh full live smoke is a **final audit** only.  Its job is to prove that the
already-tested pieces work together in a fresh environment, that failures are
traceable to concrete gates/artifacts/logs, and that the system does not hide
quality failures as readiness.

## 7. Suggested resume sequence

When tokens/time are available, resume in this order.

### Step 1 — Close the current uncommitted Repair/Convergence slice

1. Run targeted tests listed in Goal B.
2. Run full operator-feedback test file.
3. Run py_compile and diff check.
4. Run private/domain marker scan over changed files.
5. Ask Critic for implementation review.
6. Commit and push if approved.

Suggested commit intent if it passes:

```text
Carry operator rejection memory across feedback cycles
```

### Step 2 — Run current deterministic verification baseline

After the slice is committed:

```bash
.venv/bin/python -m pytest -q
scripts/pre-live-check.sh --all
```

Record evidence path.

### Step 3 — Continue Goal A/B/C with per-slice TDD verification

Do **not** run fresh full live smoke after every slice.  For each bounded slice:

1. Write or update failing unit/functional/fixture tests first.
2. Implement the minimal change.
3. Run targeted tests for that slice.
4. Run the relevant controlled smoke or pre-live check if the slice crosses
   runtime boundaries.
5. Ask Critic to verify the plan/implementation evidence.
6. Commit and push.

Use the final audit to discover integration-only bugs, not as the main proof
that a feature works.

### Step 4 — Final audit Docker fresh full live smoke

Run this only after deterministic Goal A/B/C slices are closed and the branch
is otherwise merge-auditable.

Run from a clean container/public clone with:

- Codex/OMX updated in-container;
- compile stack installed;
- private material packet mounted outside repo;
- `PAPERO_CODEX_CLI_PREFIX="omx --madmax --high --dangerously-bypass-approvals-and-sandbox"`;
- max operator cycles 5;
- max iterations 8.

Use packet root as material root, not the leaf `materials/` directory. The expected packet shape has:

- `inputs/material-manifest.json`
- `review/all-files.sha256`
- `policy/material-boundary.md`
- `materials/*`
- `figures/*`

During final audit, any bug found must be traced to a concrete artifact before
being fixed.  Record at least:

- failing command;
- relevant session/run id;
- quality gate or phase that caught the problem;
- artifact path or redacted report path;
- expected vs actual status;
- fix commit or explicit known limitation.

### Step 5 — Update public-safe evidence

After smoke:

1. Create/update redacted summary.
2. Run public/private leakage scan on committed report files.
3. Update acceptance ledger with current HEAD evidence only.
4. Keep historical evidence marked historical.

### Step 6 — Decide next quality blocker

If final smoke still says `not_ready`, choose the next bounded slice from the three quality goals:

1. Claim/Evidence/Citation quality if Tier-2 citation/claim blockers dominate.
2. Repair/Convergence if cycles repeat or fail without progress.
3. Figure/Artifact/Finalization if only human-finalization figure/export blockers remain.

Each slice still requires:

- plan;
- Critic plan approval;
- tests first;
- implementation;
- targeted/full verification;
- Critic implementation approval;
- commit/push.

## 8. Explicit non-goals / safety rails

- Do not cherry-pick only part of v1 into `main`; the user currently prefers all-or-nothing main integration.
- Do not encode private-paper/domain-specific behavior into public code.
- Do not commit private material, raw private prompts, raw private manuscript text, raw private BibTeX, or private figure/source names.
- Do not relax claim/citation hard gates to make smoke green.
- Do not treat `pass_loop_verified` as manuscript readiness.
- Do not use fresh full live smoke as a replacement for TDD/unit/functional
  verification of the feature being changed.
- Do not mark the active goal complete until the full completion audit proves all requirements.

## 9. One-line current state

The branch has a large v1 runtime with strong tests and smoke infrastructure, but it is not main-ready because Tier-2 claim/citation safety, repair convergence, and figure/finalization quality are not yet fully resolved.
