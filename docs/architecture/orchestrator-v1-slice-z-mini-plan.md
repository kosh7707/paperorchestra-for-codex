# Slice Z mini-plan — explicit one-step OMX execution entrypoint

Status: slice implementation plan requiring Critic validation before code
Date: 2026-05-13
Branch: `orchestrator-v1-runtime`

## 1. Target result

Slice Y created a bounded `OmxActionExecutor`, but it is not reachable through
high-level runtime entrypoints. Slice Z adds an explicit opt-in **one-step OMX
execution surface** so users/agents can execute the first supported OMX-required
next action after deterministic planning.

The surface remains bounded:

```text
plan state -> choose first next action -> execute only if OmxActionExecutor supports it -> record public execution evidence -> stop
```

No default behavior changes.

## 2. Public API shape

Preferred additions:

- Python: `OrchestraOrchestrator.execute_omx_once(material_path=None, runner=None, timeout_seconds=30.0)`.
- CLI: `paperorchestra orchestrate --execute-omx [--material <path>] [--write-evidence] [--json]`.
- MCP: `orchestrate({"execute_omx": true, ...})`.

Mode flags must be mutually exclusive:

```text
--execute-local
--plan-full-loop
--execute-omx
```

MCP must fail closed when more than one of `execute_local`, `plan_full_loop`,
`execute_omx` is true.

## 3. Execution source of truth

`execute_omx_once` should use the existing deterministic planning path, not a
new action planner:

1. call `run_until_blocked(material_path=...)` to build current public-safe
   state and next actions;
2. choose `state.next_actions[0]`;
3. execute it with `OmxActionExecutor` only if the adapter supports it;
4. append `orchestrator_execution_record` evidence;
5. return `OrchestratorRunResult(execution="bounded_omx_execution", action_taken=<action>)`.

The method should not silently execute multiple actions.

Mutation boundary:

- snapshot protected `OrchestraState` before `OmxActionExecutor.execute(...)`,
  matching the Slice R `step()` guard;
- executor must return `ExecutionRecord`/evidence only;
- orchestrator owns any state/evidence append;
- direct executor mutation fails closed with `ValueError`.

## 4. Safety contract

Slice Z must not:

- execute OMX unless explicitly requested;
- run deprecated `omx autoresearch`;
- launch interactive Codex sessions;
- run live model/search directly;
- draft, compile, or export manuscripts;
- treat `unsupported`, `blocked`, or `failed` as success;
- mutate state into ready/drafting/complete based only on OMX invocation.

If the first planned action is not supported by `OmxActionExecutor`, return an
`ExecutionRecord` with non-success status and no runner call.

Public result shape for all cases:

```text
execution = bounded_omx_execution
action_taken = <first planned action type> | none
execution_record = present when an action exists or deterministic no-action record is needed
```

`unsupported`, `blocked`, and `failed` records must be visible but must not
promote readiness, drafting, compile/export, or final state.

If there are no next actions, return a deterministic non-success
`ExecutionRecord(status=\"unsupported\", reason=\"no_omx_action_available\")`
without a runner call.

Runner/factory seam:

- public CLI/MCP must not accept arbitrary runner, binary, or command injection;
- implementation may use a private patchable factory/import seam for tests,
  e.g. `_make_omx_executor(cwd, timeout_seconds)`;
- runtime facade method may accept `runner` for Python tests only.

## 5. Tests to add first

### Runtime facade

`tests/test_orchestrator_omx_entrypoints.py` or existing runtime facade tests:

1. `execute_omx_once` on novelty/durable material with a fake runner executes
   `start_autoresearch_goal`, records `executed_omx`, and appends public
   `orchestrator_execution_record` evidence.
2. `execute_omx_once` on non-durable `$autoresearch` material returns
   `unsupported` / `autoresearch_skill_runtime_required` and does not call the
   runner.
3. No material/no OMX action returns non-success and does not call the runner.
4. Public result contains no raw argv, `omx ` command strings, private material,
   or absolute material paths.
5. State remains research-needed / not-ready; no drafting or readiness promotion.
6. A mutating OMX executor is rejected by the orchestrator mutation guard.

### CLI/MCP

`tests/test_orchestrator_cli_entrypoints.py` and
`tests/test_orchestrator_mcp_entrypoints.py`:

1. CLI parser accepts `--execute-omx`.
2. CLI conflicts with `--execute-local` and `--plan-full-loop` fail closed.
3. MCP schema exposes `execute_omx`.
4. MCP conflict combinations fail closed.
5. CLI/MCP can be tested with patched/fake `OmxActionExecutor` and return
   `execution=bounded_omx_execution` with execution record.
6. CLI `--execute-omx --write-evidence` writes an evidence bundle containing
   `orchestrator_execution_record`.
7. MCP `execute_omx=true, write_evidence=true` writes an evidence bundle
   containing `orchestrator_execution_record`.
8. Bundle JSON omits raw argv, `omx ` command strings, absolute material/temp
   paths, and private markers.

Conflict matrix must include:

```text
--execute-local --execute-omx
--plan-full-loop --execute-omx
execute_local=true + execute_omx=true
plan_full_loop=true + execute_omx=true
execute_local=true + plan_full_loop=true + execute_omx=true
```

### Regression

- Existing `execute_local` and `plan_full_loop` tests remain unchanged.
- `tests/test_orchestra_omx_executor.py` remains green.

## 6. Validation

Required before commit/push:

```bash
.venv/bin/python -m pytest tests/test_orchestrator_omx_entrypoints.py tests/test_orchestrator_cli_entrypoints.py tests/test_orchestrator_mcp_entrypoints.py tests/test_orchestra_omx_executor.py -q
.venv/bin/python -m pytest -q
scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
git diff --check
```

Fresh container proof after push should run the explicit OMX entrypoint tests
with fake runner patches. If the container has real `omx`, a bounded temp probe
may be recorded separately but must not be treated as manuscript readiness.

## 7. Stop/replan triggers

Stop and replan if:

- CLI/MCP execution would need raw private material or raw prompts;
- fake-runner tests require patching too much internal state to be meaningful;
- default `orchestrate`, `--execute-local`, or `--plan-full-loop` behavior
  changes;
- unsupported `$autoresearch` starts calling deprecated direct CLI;
- one request could execute more than one action.

## 8. Local implementation evidence (2026-05-13)

Issue check before resuming Slice Z:

```bash
gh issue list --state open --limit 20 --json number,title,author,createdAt,updatedAt,labels,url
# []
```

Tests-first failure was observed before implementation: missing Python facade,
CLI/MCP flags, and MCP factory/schema/conflict support. Implementation then added
only the explicit bounded OMX one-step surface.

Verification after implementation:

```bash
.venv/bin/python -m pytest tests/test_orchestrator_omx_entrypoints.py tests/test_orchestrator_cli_entrypoints.py tests/test_orchestrator_mcp_entrypoints.py -q
# 35 passed, 5 subtests passed in 0.25s

.venv/bin/python -m pytest tests/test_orchestrator_omx_entrypoints.py tests/test_orchestrator_cli_entrypoints.py tests/test_orchestrator_mcp_entrypoints.py tests/test_orchestra_omx_executor.py -q
# 46 passed, 14 subtests passed in 0.25s

.venv/bin/python -m pytest -q
# 895 passed, 146 subtests passed in 65.63s

scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
# {"status":"ok","scan_mode":"tracked_files","match_count":0,"private_safe_summary":true}

git diff --check
# ok
```

Critic implementation validation returned `APPROVE`; commit/push completed in
`be89425`. Fresh container proof is recorded below.

## 9. Fresh container proof after push (2026-05-13)

After commit `be89425` was pushed, a fresh container cloned the public remote and
checked out `orchestrator-v1-runtime` before running the Slice Z proof suite:

```bash
docker run --rm paperorchestra-ubuntu-tools:24.04 bash -lc 'set -euo pipefail; git clone --quiet https://github.com/kosh7707/paperorchestra-for-codex.git repo; cd repo; git checkout --quiet orchestrator-v1-runtime; git log -1 --oneline; python3 -m venv .venv; . .venv/bin/activate; python -m pip install --quiet -e ".[dev]"; python -m pytest tests/test_orchestrator_omx_entrypoints.py tests/test_orchestrator_cli_entrypoints.py tests/test_orchestrator_mcp_entrypoints.py tests/test_orchestra_omx_executor.py -q'
# be89425 Make bounded OMX execution explicitly opt-in
# 46 passed, 14 subtests passed in 0.40s
```
