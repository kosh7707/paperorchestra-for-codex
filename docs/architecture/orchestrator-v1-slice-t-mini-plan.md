# Slice T mini-plan — deterministic local action adapter

Status: implemented; Critic-approved after material path and local-supported policy clarifications; full-suite and leakage scan passed
Date: 2026-05-13
Branch: `orchestrator-v1-runtime`

## 1. Target result

Slice R made action execution fail closed. Slice S classified planner actions. Slice T wires the first real-but-local adapter: deterministic material/source/claim evidence generation only.

This slice proves that the orchestrator can execute a bounded local action without invoking live model/search, OMX, compile, export, or drafting paths.

```text
OrchestraOrchestrator.step(material_path=..., execute=True, executor=LocalActionExecutor(...))
-> planned local action
-> local evidence record
-> returned state gains only orchestrator-owned execution evidence
-> caller can rebuild state from artifacts/evidence later
```

## 2. Scope

Add/extend:

```text
paperorchestra/orchestra_executor.py
tests/test_orchestrator_action_executor.py
docs/architecture/orchestrator-v1-slice-t-mini-plan.md
```

No CLI/MCP default behavior changes in this slice.

## 3. Public contract

Add:

```text
LocalActionExecutor
LOCAL_SUPPORTED_ACTIONS
```

Constructor contract:

```python
LocalActionExecutor(material_path: str | Path | None = None)
```

`OrchestraState` intentionally does not expose raw material paths in public state.
Material-dependent local actions therefore use the constructor-supplied path.
If it is missing or nonexistent, those actions return `blocked` without raising.

Supported local actions:

- `inspect_material` -> `material_inventory` evidence;
- `build_source_digest` -> `material_inventory` + `source_digest` evidence;
- `build_claim_graph` -> `material_inventory` + `source_digest` + `claim_graph` evidence;
- `build_scoring_bundle` -> `scorecard_summary` evidence derived from current state.

Execution status:

- `executed_local` for successful deterministic local actions;
- `blocked` when required local inputs are absent or insufficient;
- `unsupported` for OMX/live/compile/export/user-facing actions.

`ExecutionRecord.succeeded` should be true for `executed_fake` and `executed_local` only.

## 4. Required behavior

- local execution must not mutate `OrchestraState` directly;
- `OrchestraOrchestrator.step()` mutation guard must remain effective;
- local execution may return public-safe evidence refs only;
- material paths and raw text must not appear in public execution payloads;
- `claim_graph` evidence must use `ClaimGraphReport.to_public_dict()` and never include `raw_text`;
- missing material path or missing file must return `blocked`, not crash;
- insufficient material for `build_claim_graph` must return `blocked` with public-safe source digest evidence;
- OMX-required, compile/export, and unknown actions must return `unsupported` and must not call shell/OMX/model/search/compile/export;
- `ActionExecutionPolicy` must introduce `local_supported` and classify only these four actions as local-supported:
  - `inspect_material`
  - `build_source_digest`
  - `build_claim_graph`
  - `build_scoring_bundle`
- `provide_material` must not be machine-executable; classify it as `adapter_required` for future user-intake/UI handling.
- `fake_supported` may remain only for explicit fake executor contract tests, not for real execution capability.

## 5. Tests to add first

1. `LocalActionExecutor.inspect_material` returns `executed_local` and a redacted `material_inventory` evidence ref;
2. `LocalActionExecutor.build_source_digest` returns source digest evidence without raw paths;
3. `LocalActionExecutor.build_claim_graph` returns public claim graph evidence and no `raw_text`/private material content;
4. `LocalActionExecutor.build_claim_graph` with insufficient material returns `blocked`, not an exception;
5. `LocalActionExecutor` returns `blocked` for missing material path;
6. `LocalActionExecutor` returns `unsupported` for OMX actions such as `start_autoresearch`;
7. `ExecutionRecord.succeeded` is true for `executed_local` and false for `blocked`/`unsupported`;
8. `OrchestraOrchestrator.step(... execute=True, executor=LocalActionExecutor(...))` appends only `orchestrator_execution_record` evidence and does not mutate facets/readiness/scores/hard gates;
9. no `paper_full_tex` or live command strings appear in the public result;
10. `LocalActionExecutor(material_path=...)` uses constructor-supplied path; missing path blocks;
11. policy tests assert exact `local_supported`, fake executor support, `adapter_required`, `omx_required`, and `terminal_block` sets explicitly.

## 6. Validation for this slice

Required before commit/push:

```bash
.venv/bin/python -m pytest tests/test_orchestrator_action_executor.py -q
.venv/bin/python -m pytest tests/test_orchestrator_runtime_facade.py tests/test_orchestra_materials.py tests/test_orchestra_claims.py -q
git diff --check
```

Preferred:

```bash
.venv/bin/python -m pytest -q
scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
```

Container proof after push when practical:

```bash
docker run --rm paperorchestra-ubuntu-tools:24.04 bash -lc '
  git clone https://github.com/kosh7707/paperorchestra-for-codex.git repo &&
  cd repo &&
  git checkout orchestrator-v1-runtime &&
  python3 -m venv .venv && . .venv/bin/activate &&
  python -m pip install -e ".[dev]" &&
  python -m pytest tests/test_orchestrator_action_executor.py -q
'
```

Critic plan validation is required before implementation. Critic implementation validation is required before commit.

Current evidence:

- Critic plan validation: CHANGES_REQUIRED until the material-path constructor
  contract and `local_supported` policy naming were explicit; revised plan APPROVE.
- Critic implementation validation: APPROVE.
- Targeted tests:
  - `.venv/bin/python -m pytest tests/test_orchestrator_action_executor.py -q`
    → `25 passed, 14 subtests passed`
  - `.venv/bin/python -m pytest tests/test_orchestrator_runtime_facade.py tests/test_orchestra_materials.py tests/test_orchestra_claims.py -q`
    → `16 passed`
- Final full suite: `.venv/bin/python -m pytest -q`
  → `842 passed, 127 subtests passed`
- Private leakage scan:
  `scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json`
  → `status=ok`, `scanned_file_count=200`, `match_count=0`
- Fresh container targeted proof after push:
  `docker run --rm paperorchestra-ubuntu-tools:24.04 ... git checkout orchestrator-v1-runtime ... python -m pytest tests/test_orchestrator_action_executor.py -q`
  → checkout `ab3ebbb`, `25 passed, 14 subtests passed`

## 7. Explicit non-goals

Slice T must not:

- execute live search/model calls;
- invoke OMX;
- compile/export papers;
- draft or revise manuscript text;
- create public domain-specific/private fixtures;
- change MCP/CLI defaults;
- treat local evidence generation as final readiness.

## 8. Stop/replan triggers

Stop and replan if:

- local adapter needs raw private text in public payloads;
- state mutation is required to make tests pass;
- local action execution starts to duplicate full `run_until_blocked` logic instead of returning bounded evidence;
- policy naming makes user-required actions like `provide_material` look machine-executable;
- tests require Docker, network, live providers, or private material to pass.
