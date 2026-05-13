# Slice Q mini-plan — OrchestraOrchestrator facade and bounded step contract

Status: implemented and Critic-approved
Date: 2026-05-13
Branch: `orchestrator-v1-runtime`

## 1. Target result

The architecture decision says PaperOrchestra should converge on:

```text
CLI / MCP / skill / QA loop / writing flow
        -> OrchestraOrchestrator
        -> OrchestraState
        -> validation/policies/planner
        -> bounded action/adapters
```

Current code still exposes mostly module-level functions in `paperorchestra/orchestrator.py`. Slice Q introduces an explicit `OrchestraOrchestrator` facade and a bounded step result contract while preserving existing function behavior.

This is a structure/contract slice only. It must not execute live model/search/OMX work.

## 2. Scope

Extend:

```text
paperorchestra/orchestrator.py
paperorchestra/cli.py
paperorchestra/mcp_server.py
tests/test_orchestrator_runtime_facade.py
tests/test_orchestrator_cli_entrypoints.py
tests/test_orchestrator_mcp_entrypoints.py
docs/architecture/orchestrator-v1-slice-q-mini-plan.md
```

## 3. Public contract

Add:

```text
OrchestraOrchestrator
OrchestratorRunResult
```

Minimum methods:

```text
OrchestraOrchestrator.inspect_state(material_path=None, strict_omx=False) -> OrchestraState
OrchestraOrchestrator.run_until_blocked(material_path=None) -> OrchestratorRunResult
OrchestraOrchestrator.step(material_path=None, objective=None) -> OrchestratorRunResult
```

`OrchestratorRunResult.to_public_dict()` should include:

- `execution`: `bounded_plan_only`;
- `state`: public `OrchestraState`;
- `next_actions`;
- `blocking_reasons`;
- `action_taken`: `none` for this slice;
- `private_safe=true`.

Existing module-level `inspect_state()` and `run_until_blocked()` should delegate to `OrchestraOrchestrator` and keep their current return types for compatibility.

## 4. Required behavior

- CLI/MCP high-level `orchestrate` and `continue_project` should use `OrchestraOrchestrator.run_until_blocked().to_public_dict()`;
- default CLI/MCP JSON shape should remain compatible (`execution`, `state`, and existing evidence bundle option);
- no drafting, model, search, OMX, compile, export, or private material processing is added;
- result public export must not include raw private notes;
- next actions must match the existing function/planner behavior for the same inputs;
- `step()` is a bounded alias for now: it plans and returns the current result without executing an adapter.

## 5. Tests to add first

Add/update tests before implementation:

1. `OrchestraOrchestrator.inspect_state()` returns the same public state as module `inspect_state()`;
2. `OrchestraOrchestrator.run_until_blocked()` returns `OrchestratorRunResult` with `execution=bounded_plan_only`, `action_taken=none`, and public state;
3. result public dict omits private notes/author text and includes `scorecard_summary`;
4. `step()` with insufficient material returns `provide_material` and does not execute anything;
5. CLI `orchestrate --json` still returns compatible `execution` and `state`;
6. MCP `orchestrate` still returns compatible `execution` and `state`;
7. evidence bundle writing still works when CLI/MCP use the facade;
8. no `paper_full_tex` appears in bounded result.

## 6. Validation for this slice

Required before commit/push:

```bash
.venv/bin/python -m pytest tests/test_orchestrator_runtime_facade.py tests/test_orchestrator_cli_entrypoints.py tests/test_orchestrator_mcp_entrypoints.py tests/test_mcp_server.py -q
.venv/bin/python -m pytest tests/test_orchestra_*.py tests/test_private_smoke_safety.py -q
git diff --check
```

Preferred:

```bash
.venv/bin/python -m pytest -q
scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
```

Critic plan validation is required before implementation. Critic implementation validation is required before commit.

Completed validation evidence:

```bash
.venv/bin/python -m pytest tests/test_orchestrator_runtime_facade.py tests/test_orchestrator_cli_entrypoints.py tests/test_orchestrator_mcp_entrypoints.py tests/test_mcp_server.py -q
# 21 passed

.venv/bin/python -m pytest tests/test_orchestra_*.py tests/test_private_smoke_safety.py -q
# 107 passed, 8 subtests passed

.venv/bin/python -m pytest -q
# 817 passed, 113 subtests passed

scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
# status ok, scanned_file_count=194, match_count=0

git diff --check
# clean
```

Critic implementation validation: APPROVE after adding `continue-project --write-evidence`
compatibility and tests.

## 7. Explicit non-goals

Slice Q must not:

- convert all legacy pipeline flows yet;
- execute real action adapters;
- run live model/search/OMX/compile/export work;
- change readiness or score semantics;
- break existing public CLI/MCP output keys;
- include private/domain-specific fixtures.

## 8. Stop/replan triggers

Stop and replan if:

- facade changes existing `inspect_state()` / `run_until_blocked()` semantics;
- bounded result suggests that drafting or execution happened;
- CLI/MCP output shape breaks existing tests;
- public result leaks private notes or author override text;
- tests require live providers or private material.
