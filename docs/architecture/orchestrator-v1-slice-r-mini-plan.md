# Slice R mini-plan — fake ActionExecutor contract for orchestrator steps

Status: implemented; Critic-approved after state-mutation guard; full-suite and leakage scan passed
Date: 2026-05-13
Branch: `orchestrator-v1-runtime`

## 1. Target result

Slice Q introduced `OrchestraOrchestrator` and a bounded result contract, but `step()` still only plans. Slice R adds the minimal execution abstraction needed before real adapters can be wired:

```text
OrchestraOrchestrator.step(execute=True, executor=fake)
-> select first next action
-> ActionExecutor.execute(action, state)
-> ExecutionRecord
-> OrchestratorRunResult(action_taken=..., execution=bounded_fake_execution)
```

This slice uses fake/no-op adapters only. It must not run live model/search/OMX/compile/export work.

## 2. Scope

Add/extend:

```text
paperorchestra/orchestra_executor.py
paperorchestra/orchestrator.py
tests/test_orchestrator_action_executor.py
tests/test_orchestrator_runtime_facade.py
docs/architecture/orchestrator-v1-slice-r-mini-plan.md
```

## 3. Public contract

Add:

```text
ExecutionRecord
ActionExecutor
FakeActionExecutor
```

Minimum `ExecutionRecord.to_public_dict()`:

- `schema_version`;
- `action_type`;
- `reason`;
- `status`: `planned_only | executed_fake | unsupported`;
- `adapter`: public adapter name;
- `evidence_refs`;
- `state_rebuild_required`;
- `private_safe=true`.

`FakeActionExecutor` should support a small safe allowlist:

```text
provide_material
inspect_material
build_source_digest
build_claim_graph
build_scoring_bundle
block
```

Unsupported actions return `status=unsupported` without side effects.

## 4. Required behavior

- default `OrchestraOrchestrator.step()` remains no-execution / `action_taken=none`;
- `step(execute=True, executor=None)` must fail closed with a clear `ValueError`; fake execution is never implicit;
- `step(execute=True, executor=FakeActionExecutor(...))` may execute only fake adapters;
- fake execution may mutate only by appending a public-safe execution evidence ref to the returned state/result;
- fake execution must not change facets, readiness, drafting permission, scores, hard gates, or create `paper_full_tex`;
- unsupported actions must not be silently treated as success;
- public result must include `execution_record` when execution is requested;
- execution records must not include raw prompts, argv, or private material.

## 5. Tests to add first

Add/update tests before implementation:

1. default `step()` still returns `action_taken=none` and no `execution_record`;
2. fake executor for `provide_material` returns `executed_fake`, adapter name, evidence ref, and `state_rebuild_required=true`;
3. `OrchestraOrchestrator.step(execute=True, executor=fake)` includes public execution record and top-level evidence ref;
4. fake execution does not add `paper_full_tex`, drafting permission, or ready state;
5. fake execution preserves pre/post facets and readiness except for execution evidence refs;
6. `step(execute=True)` without explicit executor fails closed;
7. unsupported action returns `unsupported` and does not claim success;
8. execution public dict redacts/omits raw private fields;
9. existing CLI/MCP high-level outputs remain bounded and do not include `execution_record` by default.

## 6. Validation for this slice

Required before commit/push:

```bash
.venv/bin/python -m pytest tests/test_orchestrator_action_executor.py tests/test_orchestrator_runtime_facade.py -q
.venv/bin/python -m pytest tests/test_orchestrator_cli_entrypoints.py tests/test_orchestrator_mcp_entrypoints.py tests/test_mcp_server.py -q
.venv/bin/python -m pytest tests/test_orchestra_*.py tests/test_private_smoke_safety.py -q
git diff --check
```

Preferred:

```bash
.venv/bin/python -m pytest -q
scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
```

Critic plan validation is required before implementation. Critic implementation validation is required before commit.

Current evidence:

- Critic plan validation: APPROVE.
- Critic implementation validation: CHANGES_REQUIRED until executor state mutation was guarded.
- Critic re-validation after guard: APPROVE.
- Targeted tests:
  - `.venv/bin/python -m pytest tests/test_orchestrator_action_executor.py tests/test_orchestrator_runtime_facade.py -q`
    → `12 passed`
  - `.venv/bin/python -m pytest tests/test_orchestrator_cli_entrypoints.py tests/test_orchestrator_mcp_entrypoints.py tests/test_mcp_server.py -q`
    → `17 passed`
  - `.venv/bin/python -m pytest tests/test_orchestra_*.py tests/test_private_smoke_safety.py -q`
    → `107 passed, 8 subtests passed`
- Final full suite: `.venv/bin/python -m pytest -q`
  → `825 passed, 113 subtests passed`
- Private leakage scan:
  `scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json`
  → `status=ok`, `scanned_file_count=196`, `match_count=0`

## 7. Explicit non-goals

Slice R must not:

- execute real PaperOrchestra pipeline functions;
- call live model/search/OMX/compile/export;
- alter CLI/MCP defaults;
- mark planned-only or fake execution as real completion;
- introduce private/domain-specific fixtures;
- change readiness/score policies.

## 8. Stop/replan triggers

Stop and replan if:

- fake execution can be mistaken for real/live execution;
- unsupported actions look successful;
- execution records leak private raw fields;
- CLI/MCP outputs change unexpectedly;
- tests require live providers, Docker, or private material for unit coverage.
