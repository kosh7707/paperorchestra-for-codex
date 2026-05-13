# Orchestrator v1 post-Slice-Z workflow plan

Status: draft meta-plan requiring Critic validation before next slice planning
Date: 2026-05-13
Branch: `orchestrator-v1-runtime`
Scope: public, domain-general workflow control plan after Slice Z. Do not include private smoke material.

## 1. Why this plan exists

The branch has accumulated many implementation slices. Before adding more runtime
behavior, the next work must re-anchor the remaining goal to a small set of
verifiable lanes. This is a **plan for the remaining plans**: no implementation
slice may start until this meta-plan receives Critic approval.

Current baseline evidence:

- GitHub open issue check before Slice Z resumed: `gh issue list --state open ...` returned `[]`.
- MCP issue #5 is closed and represented in the branch base.
- Branch `orchestrator-v1-runtime` exists and is pushed.
- Slice Z is complete:
  - `be89425 Make bounded OMX execution explicitly opt-in`
  - `cf9bb81 Record fresh proof for bounded OMX entrypoint`
- Slice Z proof:
  - local full suite: `895 passed, 146 subtests passed`;
  - leak scan: `match_count=0`;
  - Critic: `APPROVE`;
  - remote-clone container proof: `46 passed, 14 subtests passed`.

## 2. Non-negotiable workflow loop

Every remaining slice uses this sequence:

```text
open-issue check -> mini-plan -> Critic plan validation -> failing/contract tests -> implementation
-> local targeted verification -> local full verification/leak scan when relevant
-> Critic implementation validation -> commit -> push -> container proof -> evidence commit when needed
```

Additional constraints:

1. Before every slice mini-plan, check open GitHub issues and handle actionable open issues first. Record the result in the slice evidence.
2. Tests are required evidence. A behavior is not considered implemented if no
   unit/contract/functional test exercises it.
3. Docker/container proof is required for every externally visible runtime or
   onboarding change. Documentation-only evidence may use a narrower container
   proof when justified.
4. Public repo artifacts must remain domain-general. Private final-smoke material
   may be used only outside the repo and can appear in public evidence only as
   hashes, counts, redacted paths, and generic verdicts.
5. OMX invocation claims must be backed by recorded invocation/evidence artifacts.
6. Deprecated `omx autoresearch` remains forbidden.
7. `human_needed` must not be used for machine-solvable research/citation gaps.
8. Hard gates always dominate scorecards.
9. The active thread goal is not complete until a completion audit maps every
   user objective to inspected evidence. Do not call `update_goal` before then.

## 3. Remaining work lanes

### Lane A — Acceptance ledger and completion-audit harness

Problem: the branch has many acceptance gates, but no machine-readable dashboard
mapping gate -> evidence -> status.

Target:

- Add a public acceptance ledger schema for the 19 gates in
  `docs/architecture/orchestrator-v1-runtime-plan.md` section 12.
- Add a script or CLI-accessible helper that can read known evidence files and
  emit `pass | fail | blocked | unknown` per gate.
- Use this ledger as the default completion-audit artifact for future slices.

Why first: it reduces the chance that future work confuses proxy evidence with
actual objective coverage.

Test shape:

- unit tests for gate schema completeness and the exact gate ID set;
- tests proving unknown evidence stays `unknown`/`blocked`, not pass;
- tests proving private/redacted evidence fields reject raw private paths/markers;
- a public private-marker scan/redaction test for ledger evidence;
- a synthetic filled ledger test for pass/fail rendering.

### Lane B — OMX capability matrix and remaining action contracts

Problem: Slice Z exposes bounded execution, but only `record_trace_summary` and
`start_autoresearch_goal` have executable support. Other core OMX actions are
planned but unsupported.

Target:

- Create a capability matrix for each planned OMX action:
  - `start_autoresearch` — skill/runtime-only; no deprecated CLI invocation;
  - `start_deep_interview` — handoff/packet first unless safe noninteractive
    command contract is proven;
  - `start_ralplan` — handoff/packet first unless safe noninteractive command
    contract is proven;
  - `start_ralph` — handoff/packet first; interactive launch must not happen in
    one-step executor by default;
  - `start_ultraqa` — handoff/packet first;
  - `run_critic_consensus` / `run_third_critic_adjudication` — bounded local
    consensus artifact or native subagent proof, not raw OMX command guessing;
  - `record_trace_summary` — already executable;
  - `start_autoresearch_goal` — already executable.
- Expand `OmxActionExecutor` only where an exact safe command contract exists.
- For unsupported core actions, produce public-safe handoff evidence rather than
  silent `unsupported` when that improves UX.

Test shape:

- fake-runner tests for every supported command;
- handoff-evidence tests for every runtime-only action;
- conflict tests proving interactive/durable launches do not happen from a single
  bounded executor request;
- real functional probes limited to `--help`, `status`, `state`, `trace`, and toy
  `autoresearch-goal` where safe.

### Lane C — Citation quality gate hardening

Problem from private smoke: a generated PDF can contain many `Unknown` references
or weak citation support. The engine must treat citation integrity as a hard
quality concern without becoming domain-specific.

Target:

- Separate three concerns:
  1. citation need: does a sentence/claim need citation support?;
  2. citation support: does the cited source support the sentence?;
  3. citation metadata: does the BibTeX/reference identify a real source?;
- Add over-citation and duplicate-reference controls.
- Make machine research/search/S2 resolution happen before `human_needed`.
- Unknown/unsupported critical citations block readiness.

Test shape:

- synthetic manuscript with critical/ancillary claims;
- fake S2/web/source records;
- tests for Unknown critical refs blocking readiness;
- tests for irrelevant support being rejected;
- tests for duplicate/over-citation warnings vs blockers;
- no private domain terms.

### Lane D — Figure and plot replacement gate

Problem: final smoke should replace compatible placeholders with supplied figures
where safe, but must not overfit to private figure names.

Target:

- Figure asset inventory;
- figure slot plan;
- semantic slot matching using safe metadata;
- replacement report;
- final human-polish blocker when ambiguity remains.

Test shape:

- synthetic figures and slots;
- safe match, ambiguous match, no match, replacement, provenance;
- public-safe redaction of raw/private-looking names.

### Lane E — First-user orchestration and Skill/MCP UX

Problem: the intended primary UX is natural language through Codex/Skill/MCP, not
manual command memorization.

Target:

- Update skill guidance and high-level MCP/CLI fallbacks for these use cases:
  - “이 프로젝트 셋업해줘”;
  - “paperorchestra 어떻게 쓰는거야?”;
  - “이거 쓰고 싶어”;
  - “바로 써줘” with insufficient material.
- The agent should inspect state/material, run machine-solvable checks, show a
  compact five-axis status/scorecard, and ask only author-judgment questions.

Test shape:

- skill text tests against anti-patterns (README dump, low-level command dump,
  asking user for discoverable facts);
- high-level orchestrator MCP schema/response tests;
- raw MCP smoke remains green.

### Lane F — Full-loop execution policy and score/Critic consensus

Problem: `plan_full_loop` can describe next actions, but final readiness needs
phase-specific scorecards, hard-gate checks, multi-Critic consensus, and verifier
completion evidence.

Target:

- Deterministic scoring bundle builders per phase;
- fake Critic outputs with evidence-linked rationales;
- two-Critic consensus schema and disagreement/adjudication path;
- Verifier evidence checklist;
- hard-gate override tests.

Test shape:

- schema tests;
- stale manuscript hash tests;
- missing evidence tests;
- disagreement -> third adjudication action;
- high score + hard gate fail remains blocked.

### Lane G — Fresh/container/private final smoke harness

Problem: final acceptance requires a fresh full live smoke with private material
outside the repo and up to five `human_needed` cycles, but public code must remain
general-purpose.

Target:

- Prepare private material outside repo;
- add public-safe harness hooks that can run with arbitrary material folder;
- create redacted evidence summary only;
- validate that final output is near human-finalization quality, not submission
  success;
- no public private-domain terms or private-smoke identifiers.

Test shape:

- public synthetic smoke harness tests;
- private run outside repo as evidence only;
- leak scan over tracked files and exported public evidence.

## 4. Proposed execution order

1. **AA — Acceptance ledger and completion-audit harness.** This gives all later
   work a non-proxy evidence dashboard.
2. **AB — OMX capability matrix and runtime-only handoff evidence.** This closes
   the gap between planned OMX actions and actual safe invocation/handoff proof.
3. **AC — Citation quality gate hardening.** This directly targets the most
   serious private-smoke quality failure.
4. **AD — Figure gate and placeholder replacement.** This targets the supplied
   figure integration requirement.
5. **AE — First-user Skill/MCP UX refresh.** This ensures the runtime is usable
   through the intended natural-language surface.
6. **AF — Score/Critic consensus and verifier harness.** This hardens readiness
   decisions.
7. **AG — Fresh/container/private final smoke harness and redacted evidence.**
   This is final acceptance, not a substitute for prior unit/contract tests.

Order rationale:

- AA before everything: prevents losing track of huge acceptance scope.
- AB before full-loop/UX: makes OMX claims honest and testable.
- AC before final smoke: citations are the highest observed product risk.
- AD before final smoke: final PDF quality depends on figure handling.
- AE after core contracts: docs/skills should describe real behavior, not hopes.
- AF after evidence gates: Critic scoring needs complete bundles.
- AG last: integration proof only after unit/contract coverage exists.

## 5. Stop/replan triggers

Stop and replan if any slice would:

- require private material in public tests;
- add private-domain-specific heuristics or fixture names;
- treat an unsupported/failed OMX action as success;
- call deprecated `omx autoresearch`;
- ask the user for facts the system can search/inspect;
- let scorecards override hard gates;
- mark final output as submission-ready;
- skip Critic validation because tests pass;
- skip container proof for a public runtime/UX change.

## 6. Immediate next slice candidate: AA

AA is the safest next implementation slice because it changes no manuscript
behavior. It creates the evidence ledger that later slices can update.

AA mini-plan must be written and Critic-validated separately before tests or
implementation. It should define and lock the exact 19 gate IDs below:

1. `state_contract_tests`
2. `action_planner_scenario_tests`
3. `fake_omx_unit_contract_tests`
4. `real_bounded_omx_command_probes`
5. `mcp_raw_and_attach_smoke`
6. `mock_demo`
7. `compile_export`
8. `fresh_container_functional_smoke`
9. `private_final_live_smoke_redacted`
10. `private_leakage_scan`
11. `no_unsupported_critical_claims`
12. `no_unknown_refs_for_critical_claims`
13. `citation_integrity`
14. `supplied_figures_inventoried_matched_or_blocked`
15. `hard_gates_no_fail_except_human_polish`
16. `critic_consensus_near_ready_or_better`
17. `verifier_evidence_completeness_no_leakage`
18. `exported_pdf_tex_evidence_bundle`
19. `readme_environment_skill_docs_updated`

It should also define:

- ledger schema;
- allowed statuses and evidence refs;
- public-safe redaction rules;
- renderer output for human status;
- minimum tests and container proof.
