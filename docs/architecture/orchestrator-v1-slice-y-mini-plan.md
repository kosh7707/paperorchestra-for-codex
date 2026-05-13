# Slice Y mini-plan — bounded OMX action execution evidence adapter

Status: implemented locally after Critic-requested fix; awaiting final Critic approval and container proof
Date: 2026-05-13
Branch: `orchestrator-v1-runtime`

## 1. Target result

After Slice X, the main facade can plan full-loop actions, but OMX-required
planned actions still stop at public labels. Slice Y adds a **bounded OMX action
execution evidence adapter** for safe, allowlisted OMX command surfaces.

The purpose is not to run full manuscript research or launch interactive agents.
The purpose is to make OMX invocation explicit, testable, public-safe, and
fail-closed before any future full live loop depends on it.

## 2. Capability probe evidence collected before planning

Observed safe local probes in a temporary directory:

```bash
omx version
# oh-my-codex v0.17.0

omx autoresearch-goal create --topic 'Synthetic PaperOrchestra adapter probe' --rubric 'PASS if the probe creates durable public-safe artifacts only.' --slug po-synthetic-probe --json
# ok=true, writes .omx/goals/autoresearch/po-synthetic-probe/{mission.json,rubric.md,ledger.jsonl}

omx trace summary --json
# returns JSON summary without requiring an active manuscript run

omx state list-active --json
# returns JSON active_modes
```

Also observed:

```text
omx autoresearch [DEPRECATED] Use $autoresearch; direct CLI launch removed
```

So Slice Y may safely support `start_autoresearch_goal` via durable
`omx autoresearch-goal create`, but must **not** call deprecated
`omx autoresearch` for `start_autoresearch`.

## 3. Scope

Add/extend:

```text
paperorchestra/orchestra_omx_executor.py   # new bounded adapter + runner protocol
paperorchestra/orchestra_executor.py       # status/succeeded/capability integration only if needed
paperorchestra/orchestrator.py             # no default behavior changes; optional executor only if needed
paperorchestra/cli.py                      # no live default; optional future flag only if plan-approved
paperorchestra/mcp_server.py               # no live default; optional future flag only if plan-approved
tests/test_orchestra_omx_executor.py       # new fake-runner and public-safety tests
tests/test_orchestrator_action_executor.py # status/capability regressions if touched
docs/architecture/orchestrator-v1-slice-y-mini-plan.md
```

Default `orchestrate`, `--plan-full-loop`, and `--execute-local` behavior must
remain unchanged in Slice Y unless a later plan explicitly opts in an OMX
execution mode.

## 4. Execution contract

Create a thin adapter, likely:

```python
class OmxCommandRunner(Protocol):
    def run(self, argv: list[str], *, cwd: Path, timeout_seconds: float) -> OmxCommandResult: ...

class SubprocessOmxRunner: ...
class FakeOmxRunner: ...
class OmxActionExecutor:
    def __init__(self, *, cwd: Path, runner: OmxCommandRunner, timeout_seconds: float = 30.0): ...
    def execute(self, action: NextAction, state: OrchestraState) -> ExecutionRecord: ...
```

All subprocess execution must run under explicit `cwd`. The executor must not
infer cwd from process globals.

Allowed Slice Y action behavior:

| Action | Behavior |
| --- | --- |
| `record_trace_summary` | run `omx trace summary --json`, record public summary hash/status |
| `start_autoresearch_goal` | run `omx autoresearch-goal create --topic <public summary> --rubric <public rubric> --slug <stable-public-slug> --json`, record created artifact refs |
| `start_autoresearch` | fail closed / unsupported with reason `autoresearch_skill_runtime_required`; never call `omx autoresearch` |
| `start_deep_interview`, `start_ralplan`, `start_ralph`, `start_ultraqa`, critic labels | unsupported/deferred in Slice Y unless a future slice defines their exact safe command contract |

Execution status should be explicit, for example:

```text
executed_omx
blocked
unsupported
failed
```

If `ExecutionRecord.succeeded` is updated, it may include `executed_omx` only
for allowlisted successful commands. `failed`, `blocked`, `unsupported`, and
`degraded` must not count as success.

## 5. Public-safe evidence contract

Adapter evidence must include only public-safe metadata:

```json
{
  "kind": "omx_action_execution",
  "payload": {
    "schema_version": "omx-action-execution/1",
    "action_type": "start_autoresearch_goal",
    "surface": "autoresearch_goal_create",
    "command_hash": "...",
    "input_bundle_hash": "...",
    "status": "executed_omx",
    "return_code": 0,
    "artifact_refs": [".omx/goals/autoresearch/<slug>/mission.json"],
    "private_safe": true
  }
}
```

Use non-command public surface labels:

```text
trace_summary
autoresearch_goal_create
```

Do not expose raw command strings like `omx trace ...` or
`omx autoresearch-goal create` in public evidence. The raw argv may exist only
inside the runner call and tests; public evidence records hashes and stable
surface labels.

Public payload must not contain:

- raw private material;
- raw claim text;
- raw prompt text;
- raw argv list;
- shell command strings beyond stable allowlisted surface labels;
- absolute private paths;
- deprecated `omx autoresearch` command.

Topic/rubric privacy contract for `start_autoresearch_goal`:

- topic/rubric are generated from action type, canonical reason codes, public
  state hashes, and public labels only;
- topic/rubric must not include raw manuscript/material text, private notes,
  author override text, raw claim text, or absolute paths;
- evidence stores `topic_hash` and `rubric_hash`, not full topic/rubric;
- a short public label such as `PaperOrchestra evidence research goal` is
  allowed if it contains no private material.

Path containment contract:

- slug must be deterministic and public-safe, e.g. `po-<12 hex chars>`;
- reject/sanitize slug traversal (`..`), absolute paths, whitespace, control
  characters, shell metacharacters, and private markers;
- artifact refs must be relative to `cwd`;
- artifact refs must remain under `.omx/goals/autoresearch/<slug>/...`;
- absolute temp/workspace paths must never appear in public evidence.

Environment-blocker contract:

- missing `omx` binary (`FileNotFoundError`) returns non-success status with
  reason `omx_binary_missing`;
- timeout returns non-success status with reason `omx_command_timeout`;
- non-zero return code returns non-success status with reason
  `omx_command_failed`;
- none of these statuses may count as `ExecutionRecord.succeeded`.

## 6. Tests to add first

`tests/test_orchestra_omx_executor.py` should fail before implementation and
then cover:

1. Fake runner executes `record_trace_summary` and returns `executed_omx` with
   public-safe `omx_action_execution` evidence.
2. Fake runner executes `start_autoresearch_goal` using `omx autoresearch-goal
   create`, returns created artifact refs, and redacts raw topic/rubric details
   to hashes or short public summaries.
3. `start_autoresearch` is unsupported/deferred and rendered output never
   contains `omx autoresearch`.
4. Unsupported OMX actions fail closed and do not count as success.
5. Runner timeout/non-zero return code records `failed` or `blocked`, not
   success.
6. Evidence redacts `argv`, prompts, raw private text, and absolute temp paths.
7. Subprocess runner can be unit-tested with a tiny local executable/script or
   fake command without requiring actual OMX.
8. Fake runner receives exactly allowlisted argv for trace and
   autoresearch-goal create, while public evidence contains only non-command
   surface labels.
9. Missing binary (`FileNotFoundError`) maps to `omx_binary_missing`.
10. Slug/path containment rejects traversal, absolute paths, whitespace/control
    characters, shell metacharacters, and private markers.

All public evidence tests must assert absence of:

```text
argv
raw topic/rubric
absolute temp paths
omx 
omx autoresearch
PRIVATE
```

`tests/test_orchestrator_action_executor.py` should cover any changed
`ExecutionRecord.succeeded` semantics.

Optional bounded functional probe, separate from unit tests:

```bash
tmp=$(mktemp -d)
cd "$tmp"
omx autoresearch-goal create --topic 'Synthetic PaperOrchestra adapter probe' --rubric 'PASS if artifact creation works.' --slug po-synthetic-probe --json
omx trace summary --json
```

## 7. Non-goals

Slice Y must not:

- invoke deprecated `omx autoresearch`;
- run `$autoresearch` or Codex interactively;
- start long-running live research;
- call model/search providers;
- draft, compile, or export manuscripts;
- wire OMX execution into default CLI/MCP orchestration;
- treat probe success as final manuscript readiness.

## 8. Validation for this slice

Required before commit/push:

```bash
.venv/bin/python -m pytest tests/test_orchestra_omx_executor.py tests/test_orchestrator_action_executor.py -q
.venv/bin/python -m pytest -q
scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
git diff --check
```

Fresh container proof after push should run at least the fake-runner unit tests:

```bash
docker run --rm paperorchestra-ubuntu-tools:24.04 bash -lc 'set -euo pipefail; git clone --quiet https://github.com/kosh7707/paperorchestra-for-codex.git repo; cd repo; git checkout --quiet orchestrator-v1-runtime; python3 -m venv .venv; . .venv/bin/activate; python -m pip install --quiet -e ".[dev]"; python -m pytest tests/test_orchestra_omx_executor.py tests/test_orchestrator_action_executor.py -q'
```

If the image has `omx`, also record a bounded functional probe. If it does not,
record that as an environment blocker, not a product pass.

## 9. Stop/replan triggers

Stop and replan if:

- the adapter needs raw private material to form a topic/rubric;
- supporting `start_autoresearch` would require the deprecated direct CLI;
- public evidence must expose argv or command strings;
- any test uses private smoke material;
- an OMX command starts an unbounded interactive/live session;
- default CLI/MCP behavior changes without a separate opt-in plan.

## 10. Implementation validation evidence

Critic plan validation:

- First pass: `CHANGES_REQUIRED`.
- Required additions: non-command public surface labels, explicit cwd/path
  containment, missing-binary/environment blockers, topic/rubric privacy, exact
  fake-runner argv tests.
- Second pass after plan edits: `APPROVE`.

Failing tests were added before implementation. Initial targeted run failed
because `paperorchestra.orchestra_omx_executor` did not exist yet.

Implementation summary:

- Added `paperorchestra/orchestra_omx_executor.py`.
- Added `OmxCommandRunner`, `SubprocessOmxRunner`, `FakeOmxRunner`, and
  `OmxActionExecutor`.
- Added bounded support for `record_trace_summary` and
  `start_autoresearch_goal`.
- Kept `start_autoresearch` fail-closed because direct `omx autoresearch` is
  deprecated/removed.
- Added public-safe evidence with stable non-command surface labels and hashes.
- Extended `ExecutionRecord.succeeded` so only successful allowlisted OMX
  executions count as success.

Local verification:

```bash
.venv/bin/python -m pytest tests/test_orchestra_omx_executor.py tests/test_orchestrator_action_executor.py -q
# 41 passed, 22 subtests passed

.venv/bin/python -m pytest -q
# 883 passed, 137 subtests passed

scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
# status=ok, match_count=0

git diff --check
# ok
```

Bounded real OMX functional probe in a temporary directory:

```bash
tmp=$(mktemp -d)
.venv/bin/python - <<'PY' "$tmp"
from pathlib import Path
import json, sys
from paperorchestra.orchestra_omx_executor import OmxActionExecutor
from paperorchestra.orchestra_state import NextAction, OrchestraState
root = Path(sys.argv[1])
state = OrchestraState.new(cwd=root)
trace = OmxActionExecutor(cwd=root).execute(NextAction('record_trace_summary','trace_needed'), state)
goal = OmxActionExecutor(cwd=root, slug='po-abcdef123456').execute(NextAction('start_autoresearch_goal','durable_research_needed', requires_omx=True), state)
print(json.dumps({'trace': trace.to_public_dict(), 'goal': goal.to_public_dict()}, indent=2, ensure_ascii=False))
PY
# trace.status=executed_omx
# goal.status=executed_omx
# goal artifact_refs under .omx/goals/autoresearch/po-abcdef123456/
```

Critic implementation validation first pass:

- Result: `CHANGES_REQUIRED`.
- Required fix: a successful `start_autoresearch_goal` must not return
  `executed_omx` when OMX stdout is malformed or lacks durable artifact refs.
  Evidence payload also needed payload-level `action_type`.

Fix applied:

- `start_autoresearch_goal` now requires contained refs for at least
  `mission.json`, `rubric.md`, and `ledger.jsonl` under
  `.omx/goals/autoresearch/<slug>/...`.
- Empty/malformed/missing refs return `blocked` with
  `omx_artifact_refs_missing`.
- Outside/traversal refs still return `omx_artifact_ref_outside_goal`.
- `omx_action_execution.payload.action_type` is now present.

Post-fix verification:

```bash
.venv/bin/python -m pytest tests/test_orchestra_omx_executor.py tests/test_orchestrator_action_executor.py -q
# 43 passed, 26 subtests passed

.venv/bin/python -m pytest -q
# 885 passed, 141 subtests passed

scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
# status=ok, match_count=0

git diff --check
# ok
```

Post-fix bounded real OMX probe:

```json
{
  "trace_status": "executed_omx",
  "goal_status": "executed_omx",
  "goal_reason": "durable_research_needed",
  "goal_refs": [
    ".omx/goals/autoresearch/po-abcdef123456/mission.json",
    ".omx/goals/autoresearch/po-abcdef123456/rubric.md",
    ".omx/goals/autoresearch/po-abcdef123456/ledger.jsonl",
    ".omx/goals/autoresearch/po-abcdef123456/completion.json"
  ]
}
```
