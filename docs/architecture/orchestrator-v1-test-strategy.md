# PaperOrchestra v1 test strategy

Status: implementation-gating test contract for `orchestrator-v1-runtime` branch
Date: 2026-05-13
Scope: public tests use synthetic/generic fixtures only.

## 1. Test philosophy

This branch changes PaperOrchestra's runtime authority model. Tests must lock behavior before implementation.

Principles:

1. Small deterministic unit tests before runtime wiring.
2. Scenario tests for state/action transitions before full integration.
3. Fake OMX adapters for most tests; real OMX only in bounded functional/container probes.
4. Synthetic fixtures only in public tests.
5. Private final smoke material is acceptance evidence, not a public fixture.
6. Every readiness claim needs direct evidence; proxy signals are not enough.

## 2. Planned test layers

| Layer | Uses real external tools? | Purpose |
| --- | --- | --- |
| Unit | no | state validation, policies, action planning, artifact parsing |
| Contract | no or fake subprocess | JSON schema/evidence artifacts, adapter inputs/outputs |
| Functional | bounded real command probes | CLI/MCP/OMX command availability and transport compatibility |
| Container | yes, isolated | fresh clone/install/mock/compile/export/MCP attach smoke |
| Private final smoke | yes, outside repo | full live loop with private material and redacted evidence |

## 3. Unit tests to add first

The first implementation commit must add these files before production runtime code is wired:

```text
tests/test_orchestra_state_contract.py
tests/test_orchestra_state_scenarios.py
tests/test_orchestra_action_planner.py
```

They must cover the minimum cases listed in `docs/architecture/orchestrator-v1-state-contract.md`.


### 3.1 `OrchestraState` construction

Fixture: synthetic session/artifacts with minimal generic paper topic.

Tests:

- builds `no_session` when no session exists;
- builds `draft_available` from existing `SessionState` and `paper.full.tex`;
- records artifact hashes and freshness;
- supports JSON round-trip;
- public-safe export redacts raw private-like material fields.

### 3.2 `StateValidator`

Tests:

- hard-gate fail + high score is invalid for ready state;
- draft allowed without material sufficiency is invalid;
- `human_needed` for missing citation/search evidence is invalid;
- strict OMX required + missing evidence is invalid;
- stale quality score bound to old manuscript hash is invalid;
- placeholder figures without figure gate report are invalid after figure phase;
- author override cannot force claim-safe readiness.

### 3.3 `InteractionPolicy`

Tests:

- citation/source gaps -> `research_needed`;
- novelty uncertainty -> `research_needed` or `$autoresearch-goal` when durable;
- high-risk contribution framing conflict -> `human_needed`;
- central claim/evidence contradiction -> `human_needed` with alternatives;
- “write immediately” with insufficient material -> friendly block + next steps;
- machine-solvable gaps never route to `deep-interview`.

### 3.4 `ReadinessPolicy`

Tests:

- hard gates override scores;
- score bands map to readiness labels only when gates pass;
- final automation state is `ready_for_human_finalization`, not submission success;
- figure human-polish blocker may coexist with otherwise near-ready score;
- private leakage finding forces `not_ready`.

### 3.5 `ActionPlanner`

Tests:

- no session + material path -> material intake/init action;
- material inventoried + no digest -> source digest action;
- sufficient digest + no claim graph -> claim graph action;
- machine-solvable evidence gap -> `$autoresearch` action;
- durable/complex research mission -> `$autoresearch-goal` action;
- high-risk author strategy conflict -> `$deep-interview` action;
- high-risk repair strategy -> `$ralplan` action;
- repair-needed state -> `$ralph` or bounded repair action;
- QA/release objective -> `$ultraqa` action;
- compile-ready state -> compile/export action;
- no valid safe action -> blocked state with explicit next steps.

## 4. OMX integration tests

### 4.1 Fake adapter unit tests

No real OMX subprocess calls.

Tests:

- action serialization for `$autoresearch`;
- action serialization for `$autoresearch-goal`;
- action serialization for `$deep-interview`;
- action serialization for `$ralplan`;
- action serialization for `$ralph`;
- action serialization for `$ultraqa`;
- action serialization for `$trace`;
- direct `omx exec` invocation evidence schema;
- deprecated `omx autoresearch` cannot be emitted;
- raw private material is not sent to `omx explore`;
- summary-only trace export redacts raw prompts/material.

### 4.2 Contract tests

Validate artifacts:

```text
autoresearch mission / validator / completion artifact
autoresearch-goal mission / rubric / ledger / completion artifact
deep-interview transcript + answer artifact
ralplan plan + alternatives + critic verdict
ralph PRD/handoff/launch evidence
omx exec invocation evidence
trace summary evidence
```

### 4.3 Bounded functional probes

Run only where OMX is installed:

```bash
omx version
omx status
omx state list-active --json
omx trace summary --json
omx ralph --help
omx autoresearch-goal --help
omx explore --help
omx sparkshell --help
```

Functional tests must skip with explicit reason when OMX is unavailable. The final container/live smoke should not silently skip required OMX evidence.

Toy `$autoresearch-goal` lifecycle obligation where safe:

```text
create -> handoff -> status -> verdict/completion evidence
```

If the installed OMX CLI lacks a safe toy lifecycle command set, the test must record a blocker artifact and the readiness policy must treat missing durable-research evidence as non-ready in strict mode.

## 5. MCP/Skill tests

Issue #5 regression tests are already present on the branch base and must stay green.

Additional v1 tests:

- high-level orchestrator MCP tool exposes `orchestrate` / `inspect_state` / `continue_project` / `answer_human_needed` / `export_results`;
- raw MCP Content-Length smoke passes;
- raw MCP newline smoke passes;
- Codex attach smoke observes `mcp_tool_call` for a high-level tool when environment supports Codex CLI;
- skill instructions route natural-language first-use cases to high-level tools, not low-level command dumping;
- docs distinguish config registration, raw server health, attach smoke, and current conversation tool visibility.

## 6. Figure gate tests

Use synthetic figure assets only.

Tests:

- inventories supplied generic figures;
- extracts safe metadata from filenames/captions;
- matches supplied figure to compatible slot;
- refuses unsafe/ambiguous match and records human-finalization blocker;
- replaces generated placeholder when safe;
- preserves provenance and source path/hash;
- no private figure filenames/content appear in tests.

## 7. Scoring/Critic tests

LLM Critic output is hard to exact-match. Use schema and policy assertions.

Tests:

- deterministic scoring input bundle completeness;
- bundle hash binds to manuscript hash;
- missing required artifact blocks scoring;
- Critic output schema accepts evidence-linked rationale;
- Critic output without evidence links is rejected;
- two-Critic consensus artifact schema;
- unresolved Critic disagreement triggers third adjudication action;
- hard-gate fail still blocks readiness despite high score;
- score improvement can prioritize repair but cannot promote unsafe candidate.

Use fake critic outputs for unit tests. Real Critic/Verifier execution belongs to functional/private smoke evidence.

## 8. First-user scenario tests

Synthetic, no private material.

### SCN-001 setup guidance

Given a fresh checkout with venv available, `setup/intake` guidance should:

- install/check package;
- run doctor/environment summary;
- run mock smoke or point to it;
- register/smoke MCP;
- explain restart and attach distinction.

### SCN-002 “paperorchestra 어떻게 쓰는거야?”

Expected:

- concise explanation;
- offer material inspection;
- minimal intake questions;
- no README dump;
- score/status card preview.

### SCN-003 “바로 써줘” with insufficient material

Expected:

- block drafting;
- explain missing material;
- ask/propose next valid steps;
- do not fabricate claims/references.

### SCN-004 material intake to prewriting notice

Expected:

- inventory;
- digest;
- claim candidates;
- evidence obligations;
- prewriting notice;
- `draft_allowed=false` until obligations satisfy policy.

## 9. Container tests

Container/fresh QA should be used throughout but not as a replacement for unit tests.

Required before major merge:

```text
fresh container -> clone/pull branch -> install -> MCP raw smoke -> MCP attach smoke
-> mock demo -> compile if toolchain ready -> export -> pytest -> public leak scan
```

Final private smoke adds:

```text
private material prepared outside repo
orchestrate/run_until_blocked
up to required human_needed cycles with agent acting as bounded operator
compile/export evidence bundle
private leak scan
redacted public-safe summary
```

## 10. Leak/overfit tests

Add a pre-push/public safety script or test target that checks tracked files for forbidden private-smoke identifiers supplied via a local ignored denylist.

Public test fixtures must use generic names such as:

```text
example_method
example_protocol
synthetic_benchmark
supplied_architecture_diagram.pdf
```

They must not use private title, author names, private figure names, private BibTeX keys, or domain-specific acceptance wording.

## 11. Per-slice loop requirement

Every slice must execute and record:

```text
slice mini-plan -> Critic validation -> failing tests -> implementation -> implementation validation -> commit/push
```

The slice cannot proceed to the next slice on docs-only or proxy evidence.

## 12. Evidence required per implementation slice

### Slice B evidence

- state/intake unit tests pass;
- action planner unit tests pass;
- public fixtures synthetic;
- docs updated if user-facing behavior changes.

### Slice C evidence

- draft-control tests pass;
- citation/research obligation routing tests pass;
- fake OMX `$autoresearch` / `$deep-interview` routing tests pass;
- mock demo remains green or intended break is documented and fixed in same slice.

### Slice D evidence

- quality/scoring/figure/Critic consensus tests pass;
- fake and bounded real OMX probes pass;
- MCP high-level tools smoke pass;
- compile/export smoke pass;
- container QA evidence captured;
- private final smoke evidence captured outside repo.

## 13. Completion audit checklist

Before declaring the v1 goal complete, build a prompt-to-artifact checklist that maps each requirement to concrete evidence:

- plan validated by Critic;
- test spec validated by Critic;
- unit tests added before implementation;
- implementation files changed;
- targeted tests pass;
- full tests pass;
- container smoke pass;
- MCP raw + attach smoke pass;
- OMX evidence pass;
- private final smoke pass/redacted evidence;
- no unsupported critical claim in final-smoke evidence;
- no Unknown references supporting cited critical claims;
- citation integrity pass or only non-critical warnings;
- supplied figures inventoried/matched/replaced or explicit human-finalization blockers;
- hard gates pass except final human-only polish/submission tier;
- Critic consensus `near_ready` or better;
- Verifier confirms exported PDF + TeX + evidence bundle;
- no private leakage;
- docs updated;
- commit/push records exist.
