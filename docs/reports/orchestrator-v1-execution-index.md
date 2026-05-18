# Orchestrator v1 execution index

Status: draft execution index for Critic validation
Date: 2026-05-18
Branch: `orchestrator-v1-runtime`
Base: `origin/main` at `7b183fd`
Head inspected: `b53eb7f` for the execution-index commit; ledger files below were generated immediately after that commit and before the next smoke cycle.
Scope: public, domain-general execution map. Do not add private material names, raw private paths, private claims, or domain-specific smoke shortcuts.

## 1. Why this index exists

The branch is currently a single large orchestrator/runtime completion line, not a
separate v0-hardening lane plus v1 lane. It is `75` commits ahead of `origin/main`.
This index maps the interview decisions, architecture plans, slice plans,
implementation evidence, and remaining acceptance gaps so the next work can resume
without losing track of the accumulated goal.

This file is not a completion claim. It is the next planning artifact that must be
Critic-validated before another implementation or private final-smoke cycle starts.

## 2. Source artifacts inspected

- `docs/reports/orchestrator-v1-interview-decisions-redacted.md`
- `docs/architecture/orchestrator-v1-runtime-plan.md`
- `docs/architecture/orchestrator-v1-state-contract.md`
- `docs/architecture/orchestrator-v1-test-strategy.md`
- `docs/architecture/orchestrator-v1-post-z-workflow-plan.md`
- `docs/architecture/orchestrator-v1-slice-*.md`
- `docs/architecture/orchestrator-v1-tier2-quality-triage-plan.md`
- `docs/reports/orchestrator-v1-slice-ah-private-final-smoke-summary.md`
- Git range: `origin/main..HEAD`

## 3. Current branch summary

```text
origin/main..HEAD: 75 commits
branch: orchestrator-v1-runtime
head before index commit: fdfb3fb Keep author-owned citation checks visible
index commit: b53eb7f Keep orchestrator completion evidence navigable
base main: 7b183fd Make Codex MCP attachment diagnosable and compatible
```

High-level classification:

| Range | Commit topic | Classification |
| --- | --- | --- |
| 1-6 | state contract, draft control, full-loop gates, agent entrypoints | orchestrator-v1 core |
| 7-17 | private-smoke safety, material/claim/evidence, MCP evidence | orchestrator-v1 core + safety |
| 18-37 | scorecards, facade/executor/local execution, bounded OMX | orchestrator-v1 runtime |
| 38-57 | re-anchor, acceptance ledger, citation/figure/first-user/verifier gates | post-Z gates |
| 58-66 | redacted final-smoke planning/execution and generic hotfixes | private final-smoke evidence lane |
| 67-75 | Tier-2 quality hardening | post-smoke quality hardening |

## 4. Interview decision map

| # | Decision / requirement | Current status | Evidence | Remaining work |
| ---: | --- | --- | --- | --- |
| 0 | Fresh live smoke can pass system loop while manuscript remains `not_ready`; quality upgrade required. | Implemented as planning premise. | Redacted interview decisions summary; AH summary. | Re-run after T2 hardening. |
| 1 | Generation-first, Gate-first, Repair-first all required. | Partially implemented. | Material/claim/evidence modules; citation/figure/score gates; T2 repair hardening. | Prove convergence in final smoke. |
| 2 | Pre-writing contract: source digest -> contribution/claims -> evidence obligations -> prose. | Partially implemented. | `orchestra_materials.py`, `orchestra_claims.py`, `orchestra_evidence.py`, `orchestra_draft_control.py`. | Strengthen semantic quality in live run. |
| 3 | `human_needed` only for true author judgment. | Implemented in policy/tests, needs live proof. | `orchestra_policies.py`, `orchestra_planner.py`, first-user/quality tests. | Verify no machine-solvable blockers route to human in final smoke. |
| 4 | Author claim, measured evidence, and validated interpretation must be separable. | Partially implemented. | Claim/evidence graph skeleton and conflict routing. | Improve semantic conflict evidence and final proof. |
| 5 | Claim/evidence conflict policy by criticality. | Partially implemented. | Draft-control and citation/high-risk quality-loop behavior. | Verify high-criticality conflicts route correctly in final smoke. |
| 6 | Criticality strongest signals: claim type and graph position. | Implemented enough for gates. | `orchestra_draft_control.py`, `orchestra_citation_quality.py`, T2-C. | Validate live generated claims. |
| 7 | Dual graph: author claim graph and validated claim graph. | Partially implemented. | Claim/evidence structures. | Finalize richer persisted graph semantics if smoke shows gaps. |
| 8 | Scholarly quality score system, hard gates override scores. | Implemented. | `orchestra_scoring.py`, `orchestra_scorecard.py`, `orchestra_acceptance.py`. | Prove final readiness decisions are accurate. |
| 9 | 11 score dimensions; no `reviewer_attack_surface`. | Implemented. | Score dimension tests. | None before final re-verification. |
| 10 | LLM Critic-centered scoring with evidence-linked rationale. | Partially implemented. | `orchestra_consensus.py`, `orchestra_verifier.py`, AF. | Real final evidence Critic consensus still required. |
| 11 | Phase-specific scoring: prewriting, section, revision, final. | Partially implemented. | Scoring bundle/final score harness. | Broaden phase coverage as needed after final smoke. |
| 12 | Deterministic scoring input bundles with freshness/hash refs. | Implemented skeleton. | `orchestra_scoring.py`, verifier tests. | Final artifact bundle proof. |
| 13 | Readiness bands; hard gate failure => `not_ready`. | Implemented. | scorecard/readiness tests. | Final acceptance proof. |
| 14 | Scores affect repair planning, candidate promotion, readiness. | Partially implemented. | Quality-loop plan logic and T2 hardening. | Demonstrate repair progress in final smoke. |
| 15 | Open schema/reproducibility questions resolved by planning. | Partially resolved. | Runtime/post-Z plans and slice docs. | Keep unresolved items in acceptance ledger. |
| 16 | Touchpoints across quality loop, citations, Ralph bridge, CLI, smoke. | Implemented broadly. | Changed modules and tests. | No separate action. |
| 17 | Implement general-purpose scholarly quality scoring system. | Partially complete. | O/P/AF slices. | Real final Critic scoring proof. |
| 18 | First-user use cases through Codex/OMX solution flow. | Implemented. | `first_user_guide.py`, skill guidance, AE/W. | Final docs refresh after acceptance. |
| 19 | Compact user-facing scorecard shown by default. | Implemented. | P slice, inspect-state summaries. | Re-check UX in final docs. |
| 20 | Treat PaperOrchestra as engine plus guided solution. | Implemented directionally. | Runtime plan, skill/MCP entrypoints. | Final README/Skill alignment. |
| 21 | Guided intake tone: integrated agent, not CLI operator. | Implemented. | first-user guide/skill tests. | Final copy review. |
| 22 | Do not ask users for discoverable facts. | Implemented in policy, needs live proof. | interaction/action planner tests. | Confirm final smoke human_needed content. |
| 23 | Notice-first interruptible autonomy. | Partially implemented. | prewriting/draft-control logic. | Live interrupt/re-adjudication proof pending. |
| 24 | Prewriting notice must show author-responsible claim sentences. | Partially implemented. | draft-control/prewriting artifacts. | Confirm final notice quality. |
| 25 | User interruption causes re-adjudication, not direct graph mutation. | Partially implemented. | policy/action planning. | End-to-end proof pending. |
| 26 | Author override may keep claim but readiness remains BLOCK. | Implemented/hardened. | T2-D manual-check ownership policy. | Final smoke should show only true author-owned blockers. |
| 27 | Plot/figure gate; evidence plots are hard-gated. | Implemented. | `orchestra_figures.py`, AD. | Real supplied-figure smoke proof pending. |
| 28 | Use hierarchical/parallel state contract, not flat FSM. | Implemented. | `orchestra_state.py`, state contract doc/tests. | None before final audit. |
| 29 | State contract deliverables and user-facing 5-axis mapping. | Implemented with project-specific filenames. | state modules/tests and scorecard summaries. | Final UX doc check. |
| 30 | Mandatory unit/scenario/functional/container tests. | Implemented per slice. | Slice docs record tests; test suite grew past 1000 tests. | Run current full suite before final smoke/merge. |
| 31 | Test-before-implementation acceptance rule. | Mostly followed. | Mini-plans record red tests and Critic validation. | Critic should audit any weak slice evidence. |
| 32 | `OrchestraOrchestrator` is top-level runtime authority, not god object. | Partially implemented. | `orchestrator.py`, `orchestra_loop.py`, Q-X. | Full legacy absorption remains incomplete. |
| 33 | Legacy compatibility not required; Codex/MCP is main UX. | Direction accepted. | High-level entrypoints exist. | Final old-command cleanup may remain. |
| 34 | Continue vertical slices B->C->D and canonical entrypoints. | Implemented. | Slices B-D and Q-X. | Full D quality loop needs final proof. |
| 35 | Explicit OMX workflow integration and evidence artifacts. | Implemented/handoff-capable. | `orchestra_omx.py`, `orchestra_omx_executor.py`, AB/Y/Z. | Strict final smoke evidence pending. |
| 36 | Private final-smoke package is quality-target only; anti-overfit hard rule. | Partially executed safely. | AH public-safe summary; private leak scans. | Final rerun after T2; keep public tests synthetic. |
| 37 | Issue #5 MCP attach root-cause informs v1 MCP/Skill rewrite. | Implemented on main/base and preserved. | main `7b183fd`, MCP smoke scripts/tests. | Re-run attach smoke before final acceptance. |
| 38 | Final pre-goal acceptance constraints and overfit BLOCK. | Reflected in plans. | runtime/post-Z plans, T2 non-goals. | Critic must re-check final code/evidence for overfit smell. |
| 39 | Fix MCP issue on main before v1 branch. | Complete. | current base is `7b183fd`; branch created after main fix. | None. |

## 5. Slice execution map

| Slice | Target | Status | Evidence | Remaining work |
| --- | --- | --- | --- | --- |
| A | planning/docs/tests foundation | complete | runtime plan, state contract, test strategy | none |
| B | OrchestraState and intake/action planner skeleton | complete | `orchestra_state.py`, planner tests | none |
| C | draft-control policy and evidence-obligation routing | complete | `orchestra_draft_control.py`, tests | live semantic proof |
| D | full-loop gate skeleton, scoring bundles, consensus routing | complete skeleton | scoring/consensus modules and tests | final convergence proof |
| E | high-level CLI/MCP/Skill entrypoints | complete | CLI/MCP/skill tests | final UX docs check |
| F | private-smoke safety rails/material preparation | complete | prep/leak scripts/tests | rerun leak scan after final smoke |
| G | generic material inventory/source digest | complete | `orchestra_materials.py` | final smoke material intake proof |
| H | claim graph/evidence obligation skeleton | complete | `orchestra_claims.py` | richer quality if final smoke fails |
| I | public-safe evidence research mission planner | complete | `orchestra_research.py` | real autoresearch evidence pending |
| J | planned-only OMX invocation evidence adapter | complete | `orchestra_omx.py` | none |
| K | reference metadata preflight gate | complete | `orchestra_references.py` | final citation proof |
| L | orchestrator evidence bundle persistence | complete | `orchestra_evidence.py` | none |
| M | MCP evidence bundle persistence | complete | MCP tools/tests | final attach smoke |
| N | first-user guidance and MCP smoke | complete | first-user/MCP smoke tests | docs polish after final |
| O | scholarly scorecard rubric contract | complete | scoring module/tests | final Critic scoring |
| P | user-facing scorecard summary | complete | state/CLI/MCP summaries | final UX proof |
| Q | OrchestraOrchestrator facade | complete | `orchestrator.py` facade tests | full loop proof |
| R | fake ActionExecutor contract | complete | executor tests | none |
| S | action execution capability contract | complete | action capability tests | none |
| T | deterministic local action adapter | complete | local adapter tests | final live path may need more adapters |
| U | explicit local-step entrypoint wiring | complete | CLI/MCP local-step tests | none |
| V | returned-state outcome application | complete | state-advance tests | none |
| W | local-step orchestration docs | complete | documentation tests and container proof | final docs pass |
| X | full-loop planning through runtime facade | complete | full-loop planner tests | final full-loop execution proof |
| Y | bounded OMX action execution evidence adapter | complete | OMX executor tests and probes | strict final smoke evidence |
| Z | explicit one-step OMX execution entrypoint | complete | one-step tests and container proof | none |
| AA | acceptance ledger/completion audit harness | complete | `orchestra_acceptance.py`, ledger tests | ledger needs final filled evidence |
| AB | OMX capability matrix/runtime-only handoff evidence | complete | AB slice tests | final real/handoff evidence |
| AC | citation quality gate hardening | complete | `orchestra_citation_quality.py` | final citation audit |
| AD | figure gate/placeholder replacement evidence | complete | `orchestra_figures.py` | final supplied-figure proof |
| AE | first-user Skill/MCP UX guide | complete | `first_user_guide.py`, skill tests | final docs update |
| AF | score/Critic consensus/verifier harness | complete | `orchestra_consensus.py`, `orchestra_verifier.py` | real final Critic/Verifier proof |
| AG | fresh/private final-smoke acceptance summary | complete summary harness | `fresh_smoke_acceptance.py` | final rerun after T2 |
| AH | private final-smoke execution/redacted evidence | stale redacted-harness pass only; manuscript not ready | `docs/reports/orchestrator-v1-slice-ah-private-final-smoke-summary.md` | rerun after T2 hardening; do not treat AH as current v1 acceptance evidence |
| T2-A | manually orchestrated evidence freshness | implemented; validation recorded | `e1c7984`: targeted red/green tests; broader targeted suite 333 passed; full pytest 993 passed, 182 subtests; `scripts/pre-live-check.sh --all` PASS `review/pre-live-check-20260514T015154Z`; leakage scan match_count 0; Critic-approved per prior loop | include in final smoke; full private live smoke explicitly not tested in commit |
| T2-B | cited-reference provenance semantics | implemented; validation recorded | `4f6decd`: targeted provenance/action/trust tests 12 passed; targeted quality/citation suite 228 passed, 5 subtests; full pytest 1004 passed, 182 subtests; pre-live PASS `review/pre-live-check-20260514T021635Z`; leakage scan and diff check; Critic-approved per prior loop | include in final smoke; full private live smoke explicitly not tested in commit |
| T2-C | citation-density/high-risk repair effectiveness | implemented; validation recorded | `3021c8a`: targeted semantic repair tests 5 passed; targeted quality/loop suite 168 passed, 5 subtests; full pytest 1008 passed, 182 subtests; pre-live PASS `review/pre-live-check-20260514T023454Z`; leakage scan and diff check; Critic-approved per prior loop | include in final smoke; duplicate-support-specific fixture and full private live smoke remain not tested |
| T2-D | residual citation-support manual-check policy | implemented; validation recorded | `fdfb3fb`: focused manual-check tests 6 passed; targeted quality/loop suite 171 passed, 5 subtests; full pytest 1014 passed, 182 subtests; pre-live PASS `review/pre-live-check-20260514T024917Z`; leakage scan and diff check; Critic-approved per prior loop | include in final smoke; full private live smoke explicitly not tested in commit |

## 6. Public acceptance gate status

| Gate | Status | Evidence | Gap before v1 completion |
| --- | --- | --- | --- |
| `state_contract_tests` | historical-pass-known | state tests and slice evidence | rerun current full suite |
| `action_planner_scenario_tests` | historical-pass-known | action planner tests | rerun current full suite |
| `fake_omx_unit_contract_tests` | historical-pass-known | OMX fake/contract tests | rerun current full suite |
| `real_bounded_omx_command_probes` | partial | bounded probes in Y/Z | current environment proof needed |
| `mcp_raw_and_attach_smoke` | partial | issue #5 fix/smokes | current raw+attach smoke needed |
| `mock_demo` | historical-pass-known | prior container proofs | rerun before final acceptance |
| `compile_export` | historical-pass-known | prior compile/export proofs | rerun before final acceptance |
| `fresh_container_functional_smoke` | historical-pass-known | prior container proofs | rerun after final changes |
| `private_final_live_smoke_redacted` | partial | AH summary | rerun after T2 hardening |
| `private_leakage_scan` | historical-pass-known | prior scans | rerun after final smoke/docs |
| `no_unsupported_critical_claims` | fail-known/unknown | AH failed Tier-2 | prove after T2 rerun |
| `no_unknown_refs_for_critical_claims` | partial | T2-B/T2-C/T2-D | prove after T2 rerun |
| `citation_integrity` | partial | AC and T2 hardening | prove after T2 rerun |
| `supplied_figures_inventoried_matched_or_blocked` | partial | AD gate | prove with final supplied material |
| `hard_gates_no_fail_except_human_polish` | fail-known | AH `fail_tier2` | must improve or produce only true human-owned blockers |
| `critic_consensus_near_ready_or_better` | fail-known/unknown | AH not ready | final Critic consensus required |
| `verifier_evidence_completeness_no_leakage` | partial | AF verifier harness | final evidence bundle required |
| `exported_pdf_tex_evidence_bundle` | historical-pass-known | AH exported bundle | rerun final export |
| `readme_environment_skill_docs_updated` | partial | README, ENVIRONMENT, and Skill updates | final post-acceptance docs refresh |

## 7. Immediate next work

1. Critic-validate this execution index.
2. Fix this index if the Critic identifies missing goals, incorrect status, weak evidence, or unsafe assumptions.
3. Build and populate a current machine-readable acceptance ledger before private smoke; unknown or historical-only evidence must remain `unknown`/`blocked`, not pass.
4. Run a current local verification baseline:
   - targeted acceptance/orchestrator tests as needed;
   - full pytest;
   - public leakage scan;
   - MCP raw content-length smoke, raw newline smoke, and Codex attach smoke, or a documented environment blocker for any unavailable attach proof.
5. Prepare and run the T2-informed fresh full live smoke outside the public repo.
6. During smoke, explicitly check:
   - actual Ralph/OMX evidence;
   - citation integrity and support;
   - figure inventory/replacement;
   - claim/evidence conflicts;
   - scorecard movement;
   - whether `human_needed` is truly author-owned.
7. After smoke, update the acceptance ledger with fresh evidence and keep stale AH evidence marked as historical only.
8. If final smoke remains `not_ready`, convert each remaining blocker into the next bounded hardening slice with Critic plan validation before implementation.
9. If final smoke reaches `near_ready` or only true human-finalization blockers remain, perform completion audit and final documentation and merge-readiness review.

## 8. Known non-completion statement

The goal is not complete yet. The branch has strong implementation and test
coverage, but final acceptance still requires a fresh full live smoke after T2-A
through T2-D and a completion audit proving every public acceptance gate with
current evidence rather than historical proxy evidence.
