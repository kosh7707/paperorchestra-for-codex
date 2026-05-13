# Slice W mini-plan — document explicit local-step orchestration

Status: implemented; awaiting container proof after push
Date: 2026-05-13
Branch: `orchestrator-v1-runtime`

## 1. Target result

Slices T–V introduced explicit one-step local orchestration through CLI/MCP. Public docs and the PaperOrchestra skill still describe `orchestrate` as mostly plan-only, so first-use guidance is stale.

Slice W updates README, ENVIRONMENT, and skill guidance so users and Codex agents understand:

- default `orchestrate` remains bounded planning/run-until-blocked;
- `--execute-local` / `execute_local=true` performs exactly one deterministic local step;
- local execution can inspect material/source/claim/scorecard evidence but cannot run live search/model/OMX/compile/export/drafting;
- after local claim graph execution, the next action can become `$autoresearch` for machine-solvable evidence work;
- evidence bundles are diagnostics, not readiness passes.

## 2. Scope

Add/extend:

```text
README.md
ENVIRONMENT.md
skills/paperorchestra/SKILL.md
tests/test_paperorchestra_skill_guidance.py
possibly tests/test_readme_guidance.py or existing docs tests if present
docs/architecture/orchestrator-v1-slice-w-mini-plan.md
```

No runtime behavior changes in this slice.

## 3. Public documentation contract

README should include a compact “orchestrated first-use” path near the early first-run sections:

```bash
paperorchestra inspect-state --material ./my-material --json
paperorchestra orchestrate --material ./my-material --execute-local --write-evidence --json
```

It must explain:

- `--execute-local` is one local deterministic step, not a full paper run;
- no live model/search/OMX/compile/export/drafting happens;
- expected useful result is an `execution_record` plus next action such as `start_autoresearch` when evidence research is needed;
- if no material is supplied, the action is `provide_material` / `unsupported` / `material_input_required`;
- use MCP `orchestrate({material, execute_local:true, write_evidence:true})` when attached;
- use CLI fallback if MCP active attachment is absent.

Skill guidance should direct first-use Codex agents to:

- call `inspect_state` first;
- call `orchestrate` with `execute_local=true` only when the user/material path is available and a one-step local action is appropriate;
- avoid calling `execute_local` a full pipeline;
- report the execution block and next action to the user;
- not ask the user for machine-solvable search/citation work.

ENVIRONMENT should mention the local-step smoke as a no-live check below MCP smoke / environment setup.

## 4. Tests to add first

1. Skill guidance test asserts `execute_local`, `one deterministic local step`, and not-full-pipeline wording.
2. Skill guidance test asserts agents should report execution status/next action and preserve MCP registration-vs-attachment distinction.
3. Skill guidance test asserts agents should not ask the user to do machine-solvable citation/search work; they should report/route to `start_autoresearch` / `$autoresearch` instead.
4. README/skill test coverage asserts evidence bundles are diagnostic artifacts, not readiness passes.
5. README guidance test asserts README contains `--execute-local`, `execute_local`, `start_autoresearch`, and no-live boundary wording.
6. ENVIRONMENT guidance test asserts it mentions the no-live local-step check.
7. Tests should be string/guidance tests only; no runtime behavior changes.

All guidance assertions for this slice will live in the existing deterministic
file:

```text
tests/test_paperorchestra_skill_guidance.py
```

## 5. Validation for this slice

Required before commit/push:

```bash
.venv/bin/python -m pytest tests/test_paperorchestra_skill_guidance.py -q
.venv/bin/python -m pytest tests/test_orchestrator_cli_entrypoints.py tests/test_orchestrator_mcp_entrypoints.py -q
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
  python -m pytest tests/test_paperorchestra_skill_guidance.py -q
'
```

Critic plan validation is required before implementation. Critic implementation validation is required before commit.

## 6. Explicit non-goals

Slice W must not:

- change runtime behavior;
- claim local execution is full PaperOrchestra run, live search, OMX, compile, export, or drafting;
- imply evidence bundles are readiness passes;
- add private/domain-specific examples;
- require MCP active attachment for CLI fallback docs.

## 7. Stop/replan triggers

Stop and replan if:

- docs suggest `execute_local` can produce a paper draft;
- docs ask the user to do machine-solvable citation/search work by hand;
- guidance contradicts MCP registration-vs-active-attachment distinction;
- tests only check vague phrases and fail to lock the no-live/no-full-pipeline semantics.

## 8. Implementation validation evidence

Issue pre-check:

- `gh issue list --state open --limit 20 --json ...` returned `[]`.
- Issue #5 is closed and its fix commit `7b183fd` is already an ancestor of
  `orchestrator-v1-runtime`, so no issue merge was required before Slice W.

Critic implementation validation:

- Lorentz returned `APPROVE`.
- No blockers before full suite, leakage scan, container proof, and commit.

Local verification:

```bash
.venv/bin/python -m pytest tests/test_paperorchestra_skill_guidance.py -q
# 7 passed

.venv/bin/python -m pytest tests/test_orchestrator_cli_entrypoints.py tests/test_orchestrator_mcp_entrypoints.py -q
# 21 passed

git diff --check
# ok

.venv/bin/python -m pytest -q
# 861 passed, 127 subtests passed

scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
# status=ok, match_count=0
```
