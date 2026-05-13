# Slice AB mini-plan — OMX capability matrix and runtime-only handoff evidence

Status: Critic-approved mini-plan; tests must be added before implementation
Date: 2026-05-13
Branch: `orchestrator-v1-runtime`
Scope: public, domain-general OMX action capability and handoff evidence. Do not include private smoke material.

## 0. Pre-plan issue check

Required by the post-Z workflow plan before every slice mini-plan:

```bash
gh issue list --state open --limit 20 --json number,title,author,createdAt,updatedAt,labels,url
# []
```

No actionable open issue blocked Slice AB planning.

Follow-up check on 2026-05-13 after a user interruption also returned no open
GitHub issues, so this slice can proceed without reprioritizing:

```bash
gh issue list --state open --json number,title,labels,updatedAt,url --limit 20
# []
```

## 1. Target result

Slice Y made two OMX actions executable, and Slice Z exposed one-step OMX
execution through Python/CLI/MCP. Unsupported runtime-only actions currently
return a bare unsupported record with little audit value.

Slice AB adds an explicit **OMX capability matrix** and public-safe
**runtime-only handoff evidence** for core OMX actions that should not be
launched by the one-step executor.

This means:

- executable actions remain executable only when already safe;
- runtime-only actions do not call the runner;
- runtime-only actions return non-success `handoff_required` records with
  public evidence explaining the intended OMX surface and why execution is not
  performed automatically;
- deprecated direct commands remain forbidden.

## 2. Current baseline

Already executable in `OmxActionExecutor`:

- `record_trace_summary` -> `trace_summary` surface;
- `start_autoresearch_goal` -> `autoresearch_goal_create` surface.

Currently fail-closed without evidence:

- `start_autoresearch`;
- `start_deep_interview`;
- `start_ralplan`;
- `start_ralph`;
- `start_ultraqa`;
- `run_critic_consensus`;
- `run_third_critic_adjudication`.

## 3. Capability matrix contract

Add an explicit capability table for the `OmxActionExecutor` boundary, likely in
`paperorchestra/orchestra_omx_executor.py` or a small adjacent helper if that
keeps the executor simpler. This matrix is executor-specific and must not
silently change the broader `ActionExecutionPolicy.execution_kind` classification
from `omx_required`; any broader policy change requires separate tests and plan
approval.

Required public action capabilities:

| action_type | capability | public surface | runner call? | success? |
| --- | --- | --- | --- | --- |
| `record_trace_summary` | `executable` | `trace_summary` | yes | only on return code 0 |
| `start_autoresearch_goal` | `executable` | `autoresearch_goal_create` | yes | only on contained durable refs |
| `start_autoresearch` | `handoff_required` | `$autoresearch` | no | no |
| `start_deep_interview` | `handoff_required` | `$deep-interview` | no | no |
| `start_ralplan` | `handoff_required` | `$ralplan` | no | no |
| `start_ralph` | `handoff_required` | `$ralph` | no | no |
| `start_ultraqa` | `handoff_required` | `$ultraqa` | no | no |
| `run_critic_consensus` | `handoff_required` | `$critic-consensus` | no | no |
| `run_third_critic_adjudication` | `handoff_required` | `$critic-adjudication` | no | no |

Unknown action types remain `unsupported` with no runner call.

Capability statuses:

```text
executable
handoff_required
unsupported
```

Execution record statuses:

```text
executed_omx      # existing allowlisted command success only
handoff_required  # runtime-only handoff evidence; never success
unsupported       # unknown/unsupported action; never success
blocked/failed    # existing failure statuses; never success
```

`ExecutionRecord.succeeded` must remain true only for `executed_omx` and existing
safe local statuses. It must not treat `handoff_required` as success. AB must add
or update a regression test proving `ExecutionRecord(status="handoff_required")`
returns `succeeded == False`.

## 4. Handoff evidence contract

For runtime-only actions, return an `ExecutionRecord` with:

```json
{
  "action_type": "start_ralph",
  "reason": "repair_needed",
  "status": "handoff_required",
  "adapter": "omx",
  "state_rebuild_required": false,
  "evidence_refs": [
    {
      "kind": "omx_action_handoff",
      "payload": {
        "schema_version": "omx-action-handoff/1",
        "action_type": "start_ralph",
        "surface": "$ralph",
        "capability": "handoff_required",
        "reason": "repair_needed",
        "handoff_summary_hash": "...",
        "private_safe": true
      }
    }
  ]
}
```

Public evidence must not include:

- raw command strings such as `omx ralph ...` or `omx exec ...`;
- raw argv;
- raw prompts;
- raw private material, claim text, notes, or author override;
- absolute workspace/temp paths;
- deprecated `omx autoresearch` command text.

Allowed:

- stable public surface labels like `$ralph`;
- action type and reason codes;
- hashes of public summaries;
- generic explanation strings such as `runtime_only_interactive_surface`.

## 5. Entrypoint behavior

`OrchestraOrchestrator.execute_omx_once`, CLI `orchestrate --execute-omx`, and MCP
`orchestrate({execute_omx:true})` should surface handoff records the same way they
surface executed OMX records:

- choose only the first planned action;
- no runner call for handoff-required actions;
- append `orchestrator_execution_record` evidence when public handoff evidence is
  returned;
- do not mutate readiness/drafting/final state;
- do not treat handoff as success or completion.

## 6. Tests to add first

Update/add tests before implementation:

### `tests/test_orchestra_omx_executor.py`

1. Capability matrix exposes every known OMX action above with exact capability
   and public surface.
2. Handoff-required actions return `status=handoff_required`, `succeeded=false`,
   no runner calls, and one `omx_action_handoff` evidence ref.
3. Handoff evidence omits `argv`, `omx ` command strings, raw prompts, private
   notes, author override, and absolute paths.
4. `start_autoresearch` handoff evidence never contains deprecated
   `omx autoresearch` command text.
5. Unknown action remains `unsupported` with no evidence and no runner call.
6. Existing executable action tests for `record_trace_summary` and
   `start_autoresearch_goal` remain unchanged.
7. `ExecutionRecord.succeeded` is false for `handoff_required`.

### `tests/test_orchestrator_omx_entrypoints.py`

8. `execute_omx_once` on standard research-needed material returns
   `handoff_required` for `start_autoresearch`, appends public
   `orchestrator_execution_record`, and does not call the runner.
9. State remains not-ready / research-needed; no drafting/readiness promotion.

### CLI/MCP handoff tests (mandatory)

10. CLI `orchestrate --execute-omx --material <standard/non-durable synthetic material> --json`
    returns:
    - `execution=bounded_omx_execution`;
    - `action_taken=start_autoresearch`;
    - `execution_record.status=handoff_required`;
    - no raw `argv`, `omx `, private notes, or absolute material path.
11. MCP `orchestrate({execute_omx:true, material:<standard/non-durable synthetic material>})`
    asserts the same public shape.
12. At least one CLI or MCP handoff case uses `write_evidence` and proves the
    persisted evidence bundle contains `orchestrator_execution_record` without
    raw commands, private markers, or absolute material paths.
13. CLI/MCP tests must use the existing patchable `_make_omx_executor` seam or
    another explicit fake runner seam to prove no runner call occurs.

## 7. Validation before implementation commit

Local:

```bash
.venv/bin/python -m pytest tests/test_orchestra_omx_executor.py tests/test_orchestrator_omx_entrypoints.py -q
.venv/bin/python -m pytest tests/test_orchestrator_cli_entrypoints.py tests/test_orchestrator_mcp_entrypoints.py -q
.venv/bin/python -m pytest -q
scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
grep -RIn "<private-domain literal>" $(git ls-files 'docs/**' 'paperorchestra/**' 'tests/**' 'skills/**' 'README.md' 'ENVIRONMENT.md') || true
git diff --check
```

Critic implementation validation is required before commit/push.

## 8. Container proof after push

After implementation commit is pushed, run a fresh container proof:

```bash
docker run --rm paperorchestra-ubuntu-tools:24.04 bash -lc 'set -euo pipefail; git clone --quiet https://github.com/kosh7707/paperorchestra-for-codex.git repo; cd repo; git checkout --quiet orchestrator-v1-runtime; python3 -m venv .venv; . .venv/bin/activate; python -m pip install --quiet -e ".[dev]"; python -m pytest tests/test_orchestra_omx_executor.py tests/test_orchestrator_omx_entrypoints.py tests/test_orchestrator_cli_entrypoints.py tests/test_orchestrator_mcp_entrypoints.py -q'
```

Record proof in this plan or a follow-up evidence commit.

## 9. Stop/replan triggers

Stop and replan if:

- a runtime-only action would require launching interactive Codex/OMX from the
  one-step executor;
- public handoff evidence needs raw prompts or commands;
- `handoff_required` would be counted as success;
- deprecated `omx autoresearch` appears in planned or recorded command text;
- tests require private material;
- default `orchestrate`, `--execute-local`, or `--plan-full-loop` behavior changes.

## 10. Local implementation evidence

Implementation completed on 2026-05-13 after a failing-test-first pass.

Failing test evidence before implementation/fix:

- Initial AB tests failed during collection because
  `OMX_ACTION_CAPABILITIES` did not exist yet.
- Critic then found a public-safety gap for command-like unsupported actions and
  private-looking executable reasons. Added regression tests for those cases;
  they failed before the sanitizer fix.

Passing evidence after implementation:

```bash
.venv/bin/python -m pytest tests/test_orchestra_omx_executor.py \
  tests/test_orchestrator_omx_entrypoints.py \
  tests/test_orchestrator_cli_entrypoints.py \
  tests/test_orchestrator_mcp_entrypoints.py -q
# 55 passed, 30 subtests passed

.venv/bin/python -m pytest -q
# 918 passed, 177 subtests passed

git diff --check
# ok

scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
# match_count: 0
```

Critic implementation validation:

- First pass: `CHANGES_REQUIRED`; sanitize public reasons and unsupported
  command-like action types for all OMX executor records, not only handoffs.
- Second pass: `APPROVE`; no remaining blockers before commit/push/container
  proof.
