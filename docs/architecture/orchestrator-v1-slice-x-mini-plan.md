# Slice X mini-plan — expose full-loop planning through the runtime facade

Status: implemented locally after Critic-requested fix; awaiting final Critic approval and container proof
Date: 2026-05-13
Branch: `orchestrator-v1-runtime`

## 0. Plan-for-plan validation

Before writing this mini-plan, Critic validated the next-slice choice:

- Chosen path: integrate `FullLoopPlanner` into `OrchestraOrchestrator`/CLI/MCP as an explicit bounded planning surface.
- Deferred path: real OMX/autoresearch execution adapter, because the main facade should first express *when* research/critic/repair/compile/export is needed before invoking any real OMX surface.
- Deferred path: stale Slice B-F status cleanup, because it is housekeeping rather than the current runtime-coherence blocker.

Critic result: `APPROVE` with must-have constraints recorded below.

## 1. Target result

Current state after Slice W:

- `orchestra_loop.FullLoopPlanner` can plan scoring, critic consensus, repair, compile, and export transitions in unit tests.
- The primary runtime facade (`OrchestraOrchestrator`, CLI `orchestrate`, and MCP `orchestrate`) does not expose that full-loop planner as a first-class bounded planning surface.

Slice X adds an explicit **plan-only full-loop surface** so first-use agents and tests can ask:

```text
Given the current public-safe state/facts, what is the next full-loop action?
```

without executing live model/search, OMX, drafting, compile, or export.

## 2. Scope

Add/extend:

```text
paperorchestra/orchestrator.py
paperorchestra/orchestra_loop.py
paperorchestra/orchestra_consensus.py
paperorchestra/orchestra_planner.py
paperorchestra/cli.py
paperorchestra/mcp_server.py
paperorchestra/orchestra_executor.py
tests/test_orchestrator_runtime_facade.py
tests/test_orchestrator_cli_entrypoints.py
tests/test_orchestrator_mcp_entrypoints.py
tests/test_orchestrator_action_executor.py
tests/test_orchestra_full_loop_planner.py
tests/test_orchestra_consensus.py
docs/architecture/orchestrator-v1-slice-x-mini-plan.md
```

Preferred public API shape:

- Python: `OrchestraOrchestrator(...).plan_full_loop(...)` returning `OrchestratorRunResult`.
- CLI: `paperorchestra orchestrate --plan-full-loop [--json]`.
- MCP: `orchestrate({"plan_full_loop": true, ...})`.

Default `orchestrate` and `--execute-local` behavior must remain unchanged.

`--execute-local` and `--plan-full-loop` are mutually exclusive. MCP
`{"execute_local": true, "plan_full_loop": true}` must fail closed with a
deterministic validation error; it must not choose one mode silently.

## 3. Non-goals

Slice X must not:

- execute live model/search;
- execute OMX or `$autoresearch`;
- run compile/export;
- draft or revise manuscript text;
- require private smoke material;
- accept raw manuscript text or private rationale in public CLI/MCP payloads;
- present `run_critic_consensus`, `run_third_critic_adjudication`, or any `omx exec`-style surface as an executed command.

## 4. Fact-ingestion contract

Python is the only Slice X surface that may accept explicit synthetic/full-loop
facts for deterministic tests. CLI/MCP are opt-in planning smoke surfaces in
this slice; they inspect current public state/session and do not accept score or
critic fact injection yet.

Preferred Python signature:

```python
OrchestraOrchestrator(...).plan_full_loop(
    *,
    material_path: str | Path | None = None,
    state: OrchestraState | None = None,
    scoring_bundle: ScoringInputBundle | None = None,
    score: ScholarlyScore | None = None,
    consensus: CriticConsensus | None = None,
    high_risk_readiness: bool = False,
    compiled: bool = False,
    exported: bool = False,
) -> OrchestratorRunResult
```

The method builds the current public-safe `OrchestraState`, wraps the supplied
facts in `LoopFacts`, delegates to `FullLoopPlanner`, sets the returned state's
`next_actions` from `LoopDecision.actions`, and returns a public result. The
optional `state` parameter is a Python-only deterministic test seam; CLI/MCP do
not accept serialized state injection in Slice X.

No Python, CLI, or MCP public payload may include:

- raw manuscript text;
- private score rationale;
- private Critic rationale;
- raw prompts, argv, or executable commands;
- raw `paper_full_tex` contents.

## 5. Contract semantics

The full-loop plan surface must be bounded and public-safe:

```text
execution = bounded_full_loop_plan
action_taken = none
execution_record absent
```

It may plan actions such as:

```text
build_scoring_bundle
run_critic_consensus
run_third_critic_adjudication
start_ralph
match_supplied_figures
compile_current
export_results
block
```

but must not execute them.

`LoopDecision.reasons` may be copied into public `blocking_reasons` only if they
are already public-safe canonical reason codes. Otherwise they should remain
internal for Slice X.

If a session has a draft but no valid full score/consensus facts, the first full-loop action should be `build_scoring_bundle`.

If explicit test facts show:

- high score + hard gate fail -> `start_ralph` or safe block, never compile/export;
- high-risk readiness without consensus -> `run_critic_consensus`;
- critic disagreement -> `run_third_critic_adjudication`;
- consensus pass + hard gates pass + draft available -> `compile_current`;
- consensus pass + hard gates pass + compiled artifact -> `export_results`;
- placeholder figures -> `match_supplied_figures` before compile.

## 6. Action capability and surface consistency

Full-loop-only actions must be classified before they are exposed through CLI/MCP public payloads.

Required coverage:

- `run_critic_consensus` and `run_third_critic_adjudication` are OMX-required/planned-only style actions with public-safe surface metadata, not raw commands.
- `match_supplied_figures` is adapter-required/local-domain action, not fake/local-supported execution.
- Unknown command-like actions remain redacted.
- Deprecated `omx autoresearch` remains forbidden.
- `compile_current` and `export_results` remain adapter-required and must not be executed by the plan-only surface.

Pre-Slice-X `FullLoopPlanner` / `ConsensusPolicy` emitted
`omx_surface="omx exec"`. Slice X replaces that public surface with
non-command skill-style labels (`$critic-consensus`, `$critic-adjudication`)
before exposing it through facade/CLI/MCP payloads. Public payload tests must
assert no raw `"omx exec"` and no command-like `"omx "` string.

## 7. Tests to add first

Add failing/contract tests before implementation.

### Runtime facade

`tests/test_orchestrator_runtime_facade.py`:

1. `plan_full_loop` on a draft session with no score facts returns `execution=bounded_full_loop_plan` and next action `build_scoring_bundle`.
2. High score + hard gate fail returns repair/block and never `compile_current` or `export_results`.
3. High-risk readiness without consensus returns `run_critic_consensus`.
4. Consensus disagreement returns `run_third_critic_adjudication`.
5. Consensus pass + hard gates pass + draft available returns `compile_current` plan only.
6. Consensus pass + hard gates pass + compiled artifact returns `export_results` plan only.
7. Public payload redacts/omits private score rationale, critic private rationale, raw manuscript text markers, and command strings.
8. Public result shape is `execution=bounded_full_loop_plan`, `action_taken=none`, and contains no `execution_record`.

### CLI/MCP

`tests/test_orchestrator_cli_entrypoints.py` and `tests/test_orchestrator_mcp_entrypoints.py`:

1. CLI parser accepts `orchestrate --plan-full-loop`.
2. MCP schema exposes `plan_full_loop` boolean.
3. CLI/MCP plan-full-loop result preserves `execution=bounded_full_loop_plan` and does not include an `execution_record`.
4. Default `orchestrate` and `execute_local` tests remain unchanged.
5. CLI `--execute-local --plan-full-loop` fails closed.
6. MCP `{execute_local:true, plan_full_loop:true}` returns a deterministic validation error.

### Action capability

`tests/test_orchestrator_action_executor.py`:

1. Known action list/classification covers `run_critic_consensus`, `run_third_critic_adjudication`, and `match_supplied_figures`.
2. `omx exec` is not emitted as a raw public command-like action.
3. Exact classifications:
   - `run_critic_consensus`: OMX-required/planned-only style, public-safe, no raw command.
   - `run_third_critic_adjudication`: OMX-required/planned-only style, public-safe, no raw command.
   - `match_supplied_figures`: adapter-required.
   - `compile_current` / `export_results`: adapter-required.

### Full-loop and consensus cleanup

`tests/test_orchestra_full_loop_planner.py` and `tests/test_orchestra_consensus.py`:

1. Consensus/adjudication actions use public-safe non-command surfaces.
2. Rendering loop decisions/actions does not contain `"omx exec"` or `"omx "`.

## 8. Validation for this slice

Required before commit/push:

```bash
.venv/bin/python -m pytest tests/test_orchestrator_runtime_facade.py tests/test_orchestrator_cli_entrypoints.py tests/test_orchestrator_mcp_entrypoints.py tests/test_orchestrator_action_executor.py tests/test_orchestra_full_loop_planner.py tests/test_orchestra_consensus.py -q
.venv/bin/python -m pytest -q
scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
git diff --check
```

Fresh container proof after push:

```bash
docker run --rm paperorchestra-ubuntu-tools:24.04 bash -lc 'set -euo pipefail; git clone --quiet https://github.com/kosh7707/paperorchestra-for-codex.git repo; cd repo; git checkout --quiet orchestrator-v1-runtime; python3 -m venv .venv; . .venv/bin/activate; python -m pip install --quiet -e ".[dev]"; python -m pytest tests/test_orchestrator_runtime_facade.py tests/test_orchestrator_cli_entrypoints.py tests/test_orchestrator_mcp_entrypoints.py tests/test_orchestrator_action_executor.py tests/test_orchestra_full_loop_planner.py tests/test_orchestra_consensus.py -q'
```

## 9. Stop/replan triggers

Stop and replan if:

- the implementation would silently change default `orchestrate` behavior;
- full-loop planning requires raw private manuscript text in CLI/MCP arguments;
- plan-only actions look executed;
- compile/export runs instead of being planned;
- action capability classification would leak command-like strings;
- tests prove only `FullLoopPlanner` in isolation but not the runtime facade/CLI/MCP opt-in surface.

## 10. Local implementation evidence

Critic plan validation:

- First pass: `CHANGES_REQUIRED`.
- Required additions: fact-ingestion contract, execute-local/full-loop conflict
  behavior, raw `omx exec` cleanup scope, exact action classification, public
  result shape.
- Second pass after plan edits: `APPROVE`.

Failing tests were added before implementation. Initial targeted run failed for
the expected missing features:

- missing `OrchestraOrchestrator.plan_full_loop`;
- missing CLI `--plan-full-loop`;
- missing MCP `plan_full_loop`;
- missing execute-local/full-loop conflict handling;
- missing full-loop action classification;
- raw `omx exec` surfaces in consensus/full-loop actions.

Implementation summary:

- Added `OrchestraOrchestrator.plan_full_loop(...)`.
- Added CLI `orchestrate --plan-full-loop` as a mutually exclusive mode with
  `--execute-local`.
- Added MCP `plan_full_loop` boolean and fail-closed conflict handling.
- Classified `run_critic_consensus`, `run_third_critic_adjudication`, and
  `match_supplied_figures`.
- Replaced public full-loop critic surfaces with `$critic-consensus` and
  `$critic-adjudication`.

Local verification:

```bash
.venv/bin/python -m pytest tests/test_orchestrator_runtime_facade.py tests/test_orchestrator_cli_entrypoints.py tests/test_orchestrator_mcp_entrypoints.py tests/test_orchestrator_action_executor.py tests/test_orchestra_full_loop_planner.py tests/test_orchestra_consensus.py -q
# 81 passed, 17 subtests passed

.venv/bin/python -m pytest -q
# 873 passed, 130 subtests passed

scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
# status=ok, match_count=0

git diff --check
# ok
```

Critic implementation validation first pass:

- Result: `CHANGES_REQUIRED`.
- Required fix: do not add `$critic-consensus` / `$critic-adjudication` to
  `orchestra_omx.ALLOWED_SKILL_SURFACES`, because Slice X only needs
  public-safe `NextAction.omx_surface` labels, not new invocation-evidence
  adapter surfaces.

Fix applied:

- Reverted the `orchestra_omx.py` allowed-surface expansion.
- Added regression coverage that `$critic-consensus` and
  `$critic-adjudication` are not accepted by planned OMX invocation evidence
  until a future slice explicitly defines that contract.

Post-fix local verification:

```bash
.venv/bin/python -m pytest tests/test_orchestrator_runtime_facade.py tests/test_orchestrator_cli_entrypoints.py tests/test_orchestrator_mcp_entrypoints.py tests/test_orchestrator_action_executor.py tests/test_orchestra_full_loop_planner.py tests/test_orchestra_consensus.py tests/test_orchestra_omx_invocation.py -q
# 89 passed, 27 subtests passed

.venv/bin/python -m pytest -q
# 874 passed, 132 subtests passed

scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
# status=ok, match_count=0

git diff --check
# ok
```
