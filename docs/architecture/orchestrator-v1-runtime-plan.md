# PaperOrchestra v1 orchestrated runtime plan

Status: planning contract for `orchestrator-v1-runtime` branch
Date: 2026-05-13
Scope: public, domain-general design. Do not include private smoke material.

## 1. Target result

PaperOrchestra v1 should become an orchestrated paper-writing runtime rather than a loose set of CLI/MCP commands.

Accepted top-level shape:

```text
Codex / Skill / MCP / CLI fallback
        -> OrchestraOrchestrator.run_until_blocked()
        -> OrchestraState canonical world model
        -> StateValidator + ReadinessPolicy + InteractionPolicy
        -> ActionPlanner
        -> ActionExecutor / adapters
        -> artifacts + evidence
        -> rebuilt OrchestraState
```

The primary UX is natural-language through Codex/Skill/MCP. CLI remains important for tests, automation, smoke, and fallback, but it is not the conceptual primary interface.

## 2. Non-negotiable constraints

Planning dependency: `docs/architecture/orchestrator-v1-state-contract.md` is the implementation-gating state contract. Runtime code must not start until that state contract and this plan/test strategy have Critic approval.


1. **General-purpose engine:** no public code, prompt, fixture, filename rule, doc, or acceptance metric may become domain-specific to private final-smoke material.
2. **Private material boundary:** private smoke packages may be prepared and used only outside the public repo. Public evidence may contain counts, hashes, generic verdicts, and redacted paths only.
3. **Test-first:** no runtime wiring lands without unit/scenario tests that fail first or clearly prove the new contract.
4. **MCP-first foundation:** issue #5 dual-framing/Codex attach compatibility is already fixed on `main` and is the base for this branch.
5. **Hard gates override scores:** high quality scores cannot override citation, claim, privacy, compile, freshness, or provenance hard failures.
6. **Machine-solvable before human-needed:** research/source/citation gaps route to machine work first. `human_needed` is reserved for author judgment and strategy.
7. **OMX evidence is explicit:** if a stage claims OMX-backed work, an action and evidence artifact must show which OMX surface was invoked.

## 3. Why this is not a single flat FSM

The current product spans session lifecycle, claim safety, citation/search obligations, figure handling, human interaction, OMX evidence, and repair loops. A flat finite-state enum would explode and become untestable.

Use a statechart-inspired decomposition instead:

- `OrchestraState` is a typed snapshot with orthogonal facets.
- Each facet has local states and invariants.
- Cross-facet policies decide readiness and next actions.
- The orchestrator executes one bounded action at a time and rebuilds state from artifacts.

External grounding:

- Harel statecharts introduced hierarchy, concurrency/orthogonality, and communication to make complex reactive behavior more manageable than flat state diagrams.
- W3C SCXML describes a general-purpose event-based state-machine notation based on Harel statecharts, including hierarchical and parallel state structures.
- Model-based testing literature treats coverage of state-machine nodes/transitions as a concrete test-strategy concern, which maps to the state/facet transition tests in this branch.

References:

- David Harel, “Statecharts: A visual formalism for complex systems,” Science of Computer Programming, 1987: https://www.sciencedirect.com/science/article/pii/0167642387900359
- W3C, “State Chart XML (SCXML): State Machine Notation for Control Abstraction”: https://www.w3.org/TR/scxml/
- “Overview of Test Coverage Criteria for Test Case Generation from Finite State Machines Modelled as Directed Graphs”: https://arxiv.org/abs/2203.09604

## 4. Proposed state facets

The exact allowed values, event vocabulary, readiness labels, five-axis user status mapping, and hard invariants are defined in `docs/architecture/orchestrator-v1-state-contract.md`. This section is an architectural summary only; tests must use the state contract as the source of truth.


`OrchestraState` should start as an inspectable dataclass-like model that can be serialized to JSON.

Initial facets:

| Facet | Responsibility | Example states |
| --- | --- | --- |
| `session` | existing PaperOrchestra session and active artifact identity | `no_session`, `initialized`, `draft_available`, `compiled`, `blocked` |
| `material` | user-supplied material inventory and sufficiency | `missing`, `inventoried`, `insufficient`, `sufficient` |
| `source_digest` | compressed source understanding | `not_built`, `stale`, `ready`, `blocked` |
| `claims` | author vs validated claim graphs and conflicts | `missing`, `candidate`, `validated`, `conflict`, `blocked` |
| `evidence` | evidence obligations and research/source gaps | `missing`, `research_needed`, `supported`, `unresolved` |
| `citations` | citation metadata/support/integrity | `not_checked`, `unknown_refs`, `unsupported`, `supported` |
| `figures` | supplied/generated figure inventory and slot matching | `not_checked`, `placeholder_only`, `matched`, `human_finalization_needed` |
| `writing` | draft generation/prose state | `not_allowed`, `prewriting_notice`, `drafting`, `draft_available` |
| `quality` | hard gates, scores, readiness band | `not_evaluated`, `not_ready`, `repairable`, `near_ready`, `human_finalization_candidate` |
| `interaction` | user/operator intervention state | `none`, `notice`, `research_needed`, `human_needed`, `answered`, `interrupted` |
| `omx` | explicit OMX action/evidence ledger | `not_required`, `required_missing`, `evidence_present`, `degraded` |
| `artifacts` | freshness/provenance/hash facts | `unknown`, `fresh`, `stale`, `missing_required` |

Do not require all facets to be complete in the first commit. The public API should allow partial snapshots with explicit `unknown`/`not_checked` rather than pretending readiness.

## 5. Runtime components

### 5.1 `OrchestraState`

Canonical world model, rebuilt from current session/artifacts/evidence.

Must include:

- schema version;
- working directory and session identity;
- manuscript/artifact hashes;
- facet statuses;
- readiness summary;
- next valid actions;
- blocking reasons;
- public-safe provenance links.

Must not include raw private material in public-safe export mode.

### 5.2 `StateBuilder`

Builds `OrchestraState` from:

- existing `SessionState` and artifacts;
- quality gate reports;
- source obligation reports;
- citation support reports;
- figure reports;
- OMX invocation/evidence artifacts;
- operator feedback history.

### 5.3 `StateValidator`

Rejects impossible or unsafe combinations, for example:

- high readiness while hard gates fail;
- `draft_allowed` without material sufficiency or prewriting notice;
- `human_needed` for machine-solvable research gaps;
- OMX strict mode ready without OMX evidence;
- supplied figures ignored while placeholders remain unreported;
- stale score/gate artifacts bound to old manuscript hash.

### 5.4 `InteractionPolicy`

Separates user questions from machine-solvable work.

Rules:

- missing references, missing web evidence, and unresolved source support route to `research_needed` / `$autoresearch` before `human_needed`;
- high-risk claim strategy, claim strength tradeoff, contribution framing, and central evidence conflict may route to `human_needed`;
- every `human_needed` packet must include a concise explanation, alternatives, and consequences;
- “just write it” requests still trigger at least minimal intake questions and safety notices.

### 5.5 `ReadinessPolicy`

Combines hard gates, score bands, and author overrides.

Rules:

- hard gate fail => `not_ready` regardless of score;
- author override cannot force claim-safe readiness;
- a supported author override may choose a weaker/stronger framing only when evidence permits it;
- final state is at most `ready_for_human_finalization`, not submission success.

### 5.6 `ActionPlanner`

Maps state to one or more next actions. It should be deterministic for unit tests.

Examples:

- no session + material path -> `init_or_inspect_material`;
- material sufficient + no digest -> `build_source_digest`;
- machine-solvable evidence gap -> `start_autoresearch`;
- durable/complex research gap -> `start_autoresearch_goal`;
- high-risk author strategy conflict -> `start_deep_interview`;
- repairable quality failure -> `start_ralph` or bounded `qa_loop_step`;
- high-risk repair plan -> `start_ralplan`;
- final QA objective -> `start_ultraqa`;
- compile/export ready -> `compile_current` / `export_results`.

### 5.7 `ActionExecutor`

Invokes existing services through adapters. It should be thin, logged, and testable with fakes.

Adapters:

- existing PaperOrchestra CLI/pipeline functions;
- MCP tool handlers;
- skill-facing high-level instructions;
- OMX adapter;
- model/search provider adapter;
- compile/export adapter.

## 6. Canonical entrypoints

Primary:

```text
orchestrate / run_until_blocked
```

Support:

```text
inspect_state
answer_human_needed
continue_project
export_results
```

All entrypoints must return:

- current state summary;
- action taken or why no action was taken;
- blocking reasons;
- next valid actions;
- evidence artifact paths.

## 7. OMX integration policy

Core workflow surfaces:

- `$autoresearch`
- `$autoresearch-goal`
- `$deep-interview`
- `$ralplan`
- `$ralph`
- `$ultraqa`
- `$trace`

Core direct CLI surfaces:

- `omx exec`
- `omx state`
- `omx trace`
- `omx explore`
- `omx sparkshell`
- `omx status` / `omx version` / `omx doctor` / `omx help`

Forbidden:

- `omx autoresearch` legacy command.

Future optional, not v1 core:

- `$team`
- `$ultrawork`

Not a PaperOrchestra manuscript runtime primitive:

- `$ultragoal`

Every OMX action must record a public-safe invocation artifact with at least:

```json
{
  "schema_version": "omx-invocation-evidence/1",
  "surface": "$ralph",
  "purpose": "claim_safe_repair",
  "strict_required": true,
  "command_or_skill_hash": "...",
  "input_bundle_hash": "...",
  "output_ref": "...",
  "return_code": 0,
  "status": "pass | degraded | failed",
  "private_material_included": false
}
```

## 8. Scoring and Critic consensus

Scoring is not formula-only. The deterministic layer builds phase-specific evidence bundles, then LLM Critic scoring assigns scholarly scores with cited evidence.

Phases:

- prewriting;
- section/in-writing;
- revision/candidate;
- final.

Critic policy:

- single Critic is acceptable for low-risk diagnostics;
- high-risk readiness, claim conflicts, or final smoke require at least two Critic passes;
- if two Critic verdicts fail to converge after two consensus attempts, spawn a third Critic/verifier-style adjudication;
- Verifier checks final evidence completeness and leakage constraints.

Scores diagnose and prioritize repair. Hard gates decide what cannot pass.

## 9. Figure/plot gate

Figure handling must be generic.

Requirements:

- inventory supplied figure assets;
- infer candidate purpose from safe metadata such as filename/caption/context;
- map supplied assets to manuscript figure slots;
- prefer supplied assets over generated placeholders when semantically safe;
- record replacement decisions;
- leave a human-finalization blocker when final artwork/layout needs manual polish;
- never hard-code private figure names or domain-specific assumptions.

Expected generic artifacts:

```text
figure_asset_inventory.json
figure_slot_plan.json
figure_asset_slot_match.json
figure_replacement_report.json
figure_gate.json
```

## 10. Migration slices

Every slice must repeat the required loop before moving to the next slice:

```text
slice mini-plan -> Critic validation -> failing tests -> implementation -> implementation validation -> commit/push
```

If a slice cannot produce failing/contract tests first, stop and replan rather than implementing by intuition.


### Slice A — planning/docs/tests foundation

- land this plan and the test strategy;
- Critic-validate both;
- add failing/contract tests before runtime code.

### Slice B — real material intake

```text
material folder -> inventory -> source digest -> readiness -> claim candidates
-> evidence obligation map -> prewriting notice -> 5-axis status
```

### Slice C — draft control

```text
claim graph -> evidence obligations -> citation/search obligations
-> draft allowed / block / research_needed / human_needed
```

### Slice D — full paper loop

```text
draft -> citation gate -> plot gate -> scoring -> Critic consensus
-> repair -> human_needed loop -> compile/export
```

## 11. First-user use cases

### UC-001: setup after clone

Trigger:

```text
이 프로젝트 셋업해줘
```

Expected behavior:

1. create/reuse venv;
2. install PaperOrchestra;
3. run doctor/environment checks;
4. run mock demo or equivalent smoke;
5. install/register skill;
6. register MCP;
7. run MCP raw + attach smoke;
8. explain restart requirement and registration-vs-attachment distinction.

### UC-002: first use after setup

Trigger:

```text
paperorchestra 어떻게 쓰는거야?
```

Expected behavior:

- do not dump README;
- explain the natural-language path;
- offer to inspect material folder;
- start minimal intake questions;
- show a compact score/status card;
- refuse “just write it” if material is insufficient.

### UC-003: “이거 쓰고 싶어”

Expected behavior:

- infer that the user wants guided orchestration;
- inspect current repo/session/material state;
- ask only author-intent questions that cannot be discovered;
- run machine-solvable checks automatically;
- show “I will proceed this way unless interrupted” notice;
- stop at `human_needed` only for strategic author judgment.

## 12. Public acceptance gates before merge/tag

The branch is not v1-ready until all are true:

1. state contract tests pass;
2. action planner scenario tests pass;
3. fake-OMX unit/contract tests pass;
4. real bounded OMX command probes pass or produce documented environment blockers;
5. MCP raw + Codex attach smoke passes;
6. mock demo still passes;
7. compile/export still passes;
8. fresh container functional smoke passes;
9. private final live smoke runs outside repo and produces redacted evidence;
10. private leakage scan passes;
11. no unsupported critical claim remains in final-smoke evidence;
12. no Unknown references support cited critical claims;
13. citation integrity passes or leaves only non-critical warnings;
14. supplied figures are inventoried and matched/replaced where semantically safe, or explicitly listed as human-finalization blockers;
15. hard gates do not fail except final human-only polish/submission tier;
16. Critic consensus says `near_ready` or better for final smoke output;
17. Verifier confirms evidence bundle completeness and no private leakage;
18. exported PDF + TeX + evidence bundle exists;
19. README/ENVIRONMENT/Skill docs explain orchestrated runtime.

## 13. Stop conditions

Stop and replan instead of continuing implementation if:

- tests require private material to pass;
- a public fixture contains private-domain assumptions;
- `human_needed` becomes a catch-all for missing research;
- a high score can override a hard gate;
- OMX invocation evidence is missing in strict mode;
- MCP attach smoke regresses;
- the orchestrator becomes a god object instead of delegating to bounded services.
