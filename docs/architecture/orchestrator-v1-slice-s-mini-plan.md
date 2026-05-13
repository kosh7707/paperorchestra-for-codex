# Slice S mini-plan — action execution capability contract

Status: implemented; Critic-approved after command-like unsupported action redaction; full-suite and leakage scan passed
Date: 2026-05-13
Branch: `orchestrator-v1-runtime`

## 1. Target result

Slice R added a fail-closed fake `ActionExecutor`. Slice S adds a deterministic capability classifier so every planner action has an explicit execution boundary before any real adapter is wired.

The contract answers:

```text
Can this action be executed by the fake/local executor?
Does it require an OMX surface?
Does it require a future PaperOrchestra adapter?
Is it intentionally unsupported in this slice?
```

## 2. Scope

Add/extend:

```text
paperorchestra/orchestra_executor.py
tests/test_orchestrator_action_executor.py
docs/architecture/orchestrator-v1-slice-s-mini-plan.md
```

No CLI/MCP public behavior should change in this slice.

## 3. Public contract

Add:

```text
ActionCapability
ActionExecutionPolicy
```

Minimum `ActionCapability.to_public_dict()` fields:

- `schema_version`;
- `action_type`;
- `execution_kind`: `fake_supported | omx_required | adapter_required | terminal_block | unsupported`;
- `adapter_hint`;
- `requires_omx`;
- `omx_surface`;
- `risk`;
- `private_safe=true`.

`ActionExecutionPolicy.classify(action)` must classify every action emitted by `ActionPlanner` / `KNOWN_ACTIONS`.

## 4. Required behavior

- all `KNOWN_ACTIONS` have a deterministic classification;
- fake-supported actions match the Slice R fake executor allowlist;
- `start_autoresearch`, `start_autoresearch_goal`, `start_deep_interview`, `start_ralplan`, `start_ralph`, `start_ultraqa`, and `record_trace_summary` classify as `omx_required`;
- OMX actions must use canonical surfaces even if a synthetic `NextAction` omits `omx_surface`:
  - `start_autoresearch` -> `$autoresearch`
  - `start_autoresearch_goal` -> `$autoresearch-goal`
  - `start_deep_interview` -> `$deep-interview`
  - `start_ralplan` -> `$ralplan`
  - `start_ralph` -> `$ralph`
  - `start_ultraqa` -> `$ultraqa`
  - `record_trace_summary` -> `$trace`
- `compile_current` and `export_results` classify as `adapter_required`, not fake-supported;
- these future internal/user-facing actions classify as `adapter_required` until real adapters exist:
  - `build_evidence_obligations`
  - `show_prewriting_notice`
  - `re_adjudicate`
  - `auto_weaken_or_delete_claim`
- `block` classifies as `terminal_block`; `FakeActionExecutor` may still accept `block` only as a no-op evidence action and tests must document that exception;
- public `risk` is normalized to `low | medium | high | unknown`; invalid risk strings become `unknown`;
- unknown/deprecated actions classify as `unsupported` and cannot look successful;
- classification must not call shell, OMX, model/search, compile/export, or inspect private material;
- public dicts must not expose raw prompts, argv, commands, or private paths.

## 5. Tests to add first

1. every `KNOWN_ACTIONS` item has a non-unsupported classification unless intentionally listed as unsupported;
2. fake executor allowlist and policy `fake_supported` set are identical except for any explicitly documented terminal no-op;
3. OMX actions classify as `omx_required` with canonical surfaces even when the input action omits `omx_surface`;
4. compile/export classify as `adapter_required`;
5. `build_evidence_obligations`, `show_prewriting_notice`, `re_adjudicate`, and `auto_weaken_or_delete_claim` classify as `adapter_required`;
6. `block` classifies as `terminal_block`, while fake executor support for `block` is documented as a no-op exception;
7. unknown action classifies as `unsupported`;
8. invalid risk strings normalize to `unknown`;
9. capability public dict is private-safe and omits raw command/prompt fields;
10. deprecated legacy `omx autoresearch` string does not appear in policy output.

## 6. Validation for this slice

Required before commit/push:

```bash
.venv/bin/python -m pytest tests/test_orchestrator_action_executor.py -q
.venv/bin/python -m pytest tests/test_orchestra_action_planner.py tests/test_orchestrator_runtime_facade.py -q
git diff --check
```

Preferred:

```bash
.venv/bin/python -m pytest -q
scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
```

Critic plan validation is required before implementation. Critic implementation validation is required before commit.

Current evidence:

- Critic plan validation: CHANGES_REQUIRED until ambiguous action classifications,
  canonical OMX surfaces, and risk normalization were specified; revised plan APPROVE.
- Critic implementation validation: CHANGES_REQUIRED until command-like unsupported
  actions such as `omx autoresearch` were redacted from public capability output.
- Critic re-validation after redaction: APPROVE.
- Targeted tests:
  - `.venv/bin/python -m pytest tests/test_orchestrator_action_executor.py -q`
    → `17 passed, 13 subtests passed`
  - `.venv/bin/python -m pytest tests/test_orchestra_action_planner.py tests/test_orchestrator_runtime_facade.py -q`
    → `11 passed`
- Final full suite: `.venv/bin/python -m pytest -q`
  → `834 passed, 126 subtests passed`
- Private leakage scan:
  `scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json`
  → `status=ok`, `scanned_file_count=199`, `match_count=0`

## 7. Explicit non-goals

Slice S must not:

- execute any real action;
- wire real OMX/CLI/MCP/compile/export adapters;
- change CLI/MCP defaults;
- introduce private or domain-specific fixtures;
- mark unsupported or adapter-required actions as successful.

## 8. Stop/replan triggers

Stop and replan if:

- classification duplicates planner logic in a way that can drift silently;
- any live command is called;
- fake-supported classification can be confused with live execution;
- policy output leaks private strings;
- tests require private material or Docker.
