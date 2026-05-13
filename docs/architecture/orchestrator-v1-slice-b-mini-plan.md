# Slice B mini-plan — OrchestraState and intake/action-planner skeleton

Status: slice implementation plan requiring Critic validation before code
Date: 2026-05-13
Branch: `orchestrator-v1-runtime`

## 1. Target result

Implement the first minimal, tested slice of the v1 orchestrated runtime:

```text
repo/session/material facts
-> OrchestraState skeleton
-> StateValidator / InteractionPolicy / ReadinessPolicy
-> ActionPlanner
-> deterministic next actions and five-axis status
```

This slice does **not** run live models, web research, real OMX loops, full drafting, or private final smoke. It creates the tested state/action substrate that later slices will use.

## 2. Scope

### 2.1 Add public runtime modules

Proposed files:

```text
paperorchestra/orchestra_state.py
paperorchestra/orchestra_policies.py
paperorchestra/orchestra_planner.py
paperorchestra/orchestrator.py
```

Responsibilities:

- `orchestra_state.py`: dataclasses/enums/serialization/hash helpers for `OrchestraState`, facets, hard gates, five-axis status, next actions.
- `orchestra_policies.py`: `StateValidator`, `InteractionPolicy`, `ReadinessPolicy` pure logic.
- `orchestra_planner.py`: deterministic `ActionPlanner` from state to action list.
- `orchestrator.py`: minimal `inspect_state(cwd, material_path=None, strict_omx=False)` and `run_until_blocked(...)` skeleton that builds state and returns planned action without executing high-risk work.

### 2.2 Add tests before implementation

Required first tests:

```text
tests/test_orchestra_state_contract.py
tests/test_orchestra_state_scenarios.py
tests/test_orchestra_action_planner.py
```

The first test commit must fail before implementation, then pass after implementation.

### 2.3 No public private-material references

Public fixtures must be synthetic/generic only, e.g.:

```text
synthetic_method
example_protocol
example_benchmark
supplied_architecture_diagram.pdf
```

Forbidden in public code/tests/docs:

- private paper title/abbreviations;
- private figure filenames;
- private BibTeX keys;
- private claim wording;
- domain-specific acceptance shortcuts.

## 3. Minimal implementation behavior

### 3.1 `OrchestraState`

Must support:

- schema version `orchestra-state/1`;
- default facets with explicit non-ready values;
- JSON round-trip;
- public-safe export mode;
- manuscript hash if a `paper.full.tex` path is present in the existing `SessionState` artifact index;
- `blocking_reasons` and `next_actions`.

### 3.2 `StateBuilder` / inspection skeleton

In this slice, the builder may be conservative and mostly derived from existing session/material facts:

- no current session -> `session=no_session`;
- provided material path exists but not inventoried -> `material=inventory_needed` and action `inspect_material`;
- missing material -> `material=missing` and readiness `needs_material`;
- current session with `paper.full.tex` -> `session=draft_available`;
- current session with `compiled_pdf` -> `session=compiled`;
- no source digest/claim graph/evidence artifacts -> corresponding facets remain `missing`/`not_checked`.

Do not pretend source digest, claim graph, citation support, or figure matching exists unless artifact evidence exists.

### 3.3 Policies

Implement enough pure policy logic to satisfy contract tests:

- hard gate failure overrides high score;
- machine-solvable citation/source gaps become `research_needed`, not `human_needed`;
- durable research gaps plan `$autoresearch-goal`;
- high-risk claim/evidence conflict routes to `human_needed`;
- author override cannot force readiness;
- prewriting notice is required before drafting;
- user interrupt plans `re_adjudicate`;
- unresolved placeholder figures produce blocker or human-finalization blocker;
- deprecated `omx autoresearch` is impossible.

### 3.4 `ActionPlanner`

Minimum action names:

```text
inspect_material
build_source_digest
build_claim_graph
build_evidence_obligations
show_prewriting_notice
start_autoresearch
start_autoresearch_goal
start_deep_interview
start_ralplan
start_ralph
start_ultraqa
record_trace_summary
re_adjudicate
compile_current
export_results
block
```

Every action should include:

```json
{
  "action_type": "start_autoresearch_goal",
  "reason": "durable_research_needed",
  "requires_omx": true,
  "omx_surface": "$autoresearch-goal",
  "risk": "medium",
  "evidence_required": true
}
```

No action may use the legacy command string `omx autoresearch`.

## 4. Test cases for this slice

### 4.1 `tests/test_orchestra_state_contract.py`

- state defaults are non-ready and JSON round-trip;
- hard gate fail overrides high score;
- author override cannot force readiness;
- public-safe export redacts/omits private raw fields;
- deprecated `omx autoresearch` does not appear in known actions.

### 4.2 `tests/test_orchestra_state_scenarios.py`

- no session + no material -> `needs_material` + action guidance;
- material path provided -> `inventory_needed` + `inspect_material` action;
- synthetic current session with `paper.full.tex` -> `draft_available` with manuscript hash;
- prewriting notice required before drafting;
- user interrupt -> `re_adjudicate` action;
- unresolved placeholder figure -> figure blocker or human-finalization blocker.

### 4.3 `tests/test_orchestra_action_planner.py`

- citation/source gap -> `start_autoresearch`, not `start_deep_interview`;
- durable research gap -> `start_autoresearch_goal`;
- high-risk claim conflict -> `start_deep_interview`;
- high-risk repair -> `start_ralplan`;
- repair-needed -> `start_ralph`;
- QA objective -> `start_ultraqa`;
- strict OMX required + missing evidence -> readiness block / evidence-required action.

## 5. Validation for this slice

Required before commit/push:

```bash
python3 -m pytest \
  tests/test_orchestra_state_contract.py \
  tests/test_orchestra_state_scenarios.py \
  tests/test_orchestra_action_planner.py -q
python3 -m pytest tests/test_mcp_server.py tests/test_pre_live_check_script.py -q
git diff --check
```

Preferred if time permits:

```bash
python3 -m pytest -q
```

Critic implementation validation is required before commit.

## 6. Explicit non-goals

This slice must not:

- rewrite existing pipeline generation;
- expose new MCP tools yet;
- invoke real OMX workflows;
- run private final smoke;
- alter demo/compile/export behavior except through tests proving no regression;
- add dependencies;
- hard-code any private-domain facts.

## 7. Stop/replan triggers

Stop and replan if:

- tests require private material;
- action planning becomes ambiguous enough to need user semantics not in the state contract;
- code starts duplicating existing pipeline behavior instead of wrapping/inspecting it;
- implementing a policy requires weakening hard-gate semantics;
- MCP issue #5 transport tests regress.
