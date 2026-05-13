# Slice U mini-plan — explicit local-step entrypoint wiring

Status: implemented; Critic-approved after non-JSON execution summary fix; full-suite and leakage scan passed
Date: 2026-05-13
Branch: `orchestrator-v1-runtime`

## 1. Target result

Slice T introduced `LocalActionExecutor`, but only direct Python callers can use it. Slice U exposes that executor through CLI/MCP as an explicit opt-in one-step operation while preserving all defaults.

```text
paperorchestra orchestrate --material <path> --execute-local --json
MCP orchestrate({material, execute_local: true})
-> OrchestraOrchestrator.step(... execute=True, executor=LocalActionExecutor(material_path=...))
-> public execution_record
-> optional write_evidence includes execution evidence
```

This is a one-step local execution surface, not a live/full pipeline.

## 2. Scope

Add/extend:

```text
paperorchestra/cli.py
paperorchestra/mcp_server.py
tests/test_orchestrator_cli_entrypoints.py
tests/test_orchestrator_mcp_entrypoints.py
docs/architecture/orchestrator-v1-slice-u-mini-plan.md
```

No default behavior changes: without the new opt-in flag, CLI/MCP outputs must remain bounded plan/run-until-blocked as before.

## 3. Public contract

CLI:

```bash
paperorchestra orchestrate --material MATERIAL --execute-local [--write-evidence] [--json]
```

MCP:

```json
{"name": "orchestrate", "arguments": {"material": "...", "execute_local": true}}
```

Behavior:

- `execute_local=false` / omitted: existing `run_until_blocked` behavior;
- `execute_local=true`: execute exactly one planned local step with `LocalActionExecutor(material_path=material)`;
- if no explicit material is supplied, local execution is still safe and should return an unsupported/blocked execution record rather than crashing;
- `write_evidence=true` persists a public-safe evidence bundle containing the execution record evidence;
- output must clearly say `execution=bounded_local_execution` or equivalent and include `execution_record`;
- `OrchestraOrchestrator.step()` must stop reporting local execution as `bounded_fake_execution`.
  Fake executor records keep `execution=bounded_fake_execution`; local executor records use
  `execution=bounded_local_execution`; unsupported/blocked local opt-in results use the
  selected executor family rather than pretending fake execution.
- `execute_local=true` without material is deterministic: the planner selects
  `provide_material`, `LocalActionExecutor` returns `execution_record.status=unsupported`,
  `action_type=provide_material`, and a clear public reason that material input is required.
- no live model/search, OMX, compile/export, or drafting.

## 4. Required behavior

- CLI/MCP schemas/help expose the opt-in flag;
- default CLI/MCP tests continue to assert no `execution_record` by default;
- opt-in local execution includes an execution record;
- opt-in write-evidence manifest includes an `orchestrator_execution_record` evidence entry;
- material path/root/raw content must not leak in public payload or evidence bundle;
- no `paper_full_tex`, `omx `, `codex `, compile/export command, or live provider string appears;
- the one-step result must preserve state mutation guard semantics.

## 5. Tests to add first

1. CLI parser accepts `orchestrate --execute-local`;
2. CLI default `orchestrate` still omits `execution_record`;
3. CLI `orchestrate --material ... --execute-local --json` returns `execution_record.status=executed_local` for sufficient synthetic material;
4. CLI `--execute-local --write-evidence` writes a manifest containing `orchestrator_execution_record` evidence;
5. MCP tool schema includes `execute_local` boolean;
6. MCP default `orchestrate` still omits `execution_record`;
7. MCP `execute_local=true` returns local execution record;
8. CLI and MCP `execute_local=true` without material return unsupported `provide_material` execution records rather than crashing;
9. fake executor tests still see `execution=bounded_fake_execution`, while local executor/entrypoint tests see `execution=bounded_local_execution`;
10. public CLI/MCP/evidence text omits raw material content, temp path, `paper_full_tex`, `omx `, and `codex `.

## 6. Validation for this slice

Required before commit/push:

```bash
.venv/bin/python -m pytest tests/test_orchestrator_cli_entrypoints.py tests/test_orchestrator_mcp_entrypoints.py tests/test_orchestrator_action_executor.py -q
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
  cd repo && git checkout orchestrator-v1-runtime &&
  python3 -m venv .venv && . .venv/bin/activate &&
  python -m pip install -e ".[dev]" &&
  python -m pytest tests/test_orchestrator_cli_entrypoints.py tests/test_orchestrator_mcp_entrypoints.py -q
'
```

Critic plan validation is required before implementation. Critic implementation validation is required before commit.

Current evidence:

- Critic plan validation: CHANGES_REQUIRED until fake/local execution labels and
  no-material opt-in behavior were specified; revised plan APPROVE.
- Critic implementation validation: CHANGES_REQUIRED until CLI non-JSON
  `--execute-local` output printed an explicit execution block; re-validation APPROVE.
- Targeted tests:
  - `.venv/bin/python -m pytest tests/test_orchestrator_cli_entrypoints.py tests/test_orchestrator_mcp_entrypoints.py tests/test_orchestrator_action_executor.py -q`
    → `46 passed, 14 subtests passed`
- Final full suite: `.venv/bin/python -m pytest -q`
  → `850 passed, 127 subtests passed`
- Private leakage scan:
  `scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json`
  → `status=ok`, `scanned_file_count=201`, `match_count=0`

## 7. Explicit non-goals

Slice U must not:

- make local execution default;
- run more than one local step;
- invoke OMX/live model/search/compile/export;
- draft or revise manuscript text;
- change `continue-project` behavior unless separately planned;
- introduce private/domain-specific fixtures.

## 8. Stop/replan triggers

Stop and replan if:

- default CLI/MCP behavior changes;
- opt-in local execution can be confused with a full pipeline run;
- public payload/evidence leaks raw material, absolute paths, or command strings;
- implementation needs broad CLI/MCP rewrites rather than a small opt-in branch.
