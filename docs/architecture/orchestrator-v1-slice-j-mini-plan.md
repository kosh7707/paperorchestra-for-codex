# Slice J mini-plan — planned-only OMX invocation evidence adapter

Status: implemented; plan and implementation validated by Critic before commit
Date: 2026-05-13
Branch: `orchestrator-v1-runtime`

## 1. Target result

Convert planned `NextAction`/research mission routing into a public-safe OMX invocation evidence record without executing OMX:

```text
evidence research mission
-> planned OMX invocation evidence
-> desired skill surface + input bundle hash
-> execution_status=planned_only
-> OrchestraState evidence_refs include omx_invocation_evidence
```

This slice is a contract/adapter skeleton. It does not run `omx`, spawn Codex, or mark OMX evidence as executed.

## 2. Why this slice exists

Previous slices introduced `$autoresearch`/`$autoresearch-goal` routing. The next risk is ambiguity: a user or downstream gate might mistake planned routing for actual OMX execution. Slice J makes the boundary explicit.

It should answer:

- which OMX skill surface is planned;
- what purpose the surface serves;
- which public-safe input bundle was hashed;
- whether strict execution evidence is still missing;
- whether any private material was included in the public evidence.

## 3. Public module and integration points

Proposed file:

```text
paperorchestra/orchestra_omx.py
```

Types/functions:

```text
OmxInvocationEvidence
build_planned_omx_invocation_evidence(...)
build_research_mission_invocation_evidence(mission)
```

Integrate conservatively with:

```text
paperorchestra/orchestrator.py
```

When `run_until_blocked(..., material_path=...)` records an `evidence_research_mission`, it may also record a planned `omx_invocation_evidence` ref for the desired skill surface.

## 4. Allowed surface policy

Allowed planned skill surfaces for this slice:

```text
$autoresearch
$autoresearch-goal
$deep-interview
$ralplan
$ralph
$ultraqa
$trace
```

The deprecated direct legacy autoresearch command string must be rejected. Planned evidence must store skill surfaces, not shell commands.

`omx exec` is not part of this slice. It will get a separate direct-exec evidence contract later because its command/execution semantics differ from skill-surface planning.

## 5. Evidence schema policy

Planned evidence public payload should include:

- `schema_version="omx-invocation-evidence/1"`;
- `surface`;
- `purpose`;
- `strict_required`;
- `command_or_skill_hash`;
- `input_bundle_hash`;
- `output_ref=null`;
- `return_code=null`;
- `status="planned"`;
- `execution_status="planned_only"`;
- `private_material_included=false`;
- `private_safe_summary=true`.

It must not include raw prompts, raw claim text, raw source text, private paths, or executable command argv by default.

## 6. Tests to add first

Proposed file:

```text
tests/test_orchestra_omx_invocation.py
```

Minimum tests:

1. planned `$autoresearch` evidence emits schema, planned_only, null return_code/output_ref, and stable hashes;
2. planned `$autoresearch-goal` evidence is accepted for durable missions;
3. deprecated direct legacy autoresearch command string is rejected;
4. public evidence hashes input but does not include raw private marker text;
5. `run_until_blocked(material_path=...)` with synthetic novelty material records `omx_invocation_evidence` with `$autoresearch-goal` and `planned_only`;
6. planned-only evidence does not set `return_code=0` or `status=pass`.

## 7. Validation for this slice

Required before commit/push:

```bash
.venv/bin/python -m pytest tests/test_orchestra_omx_invocation.py tests/test_orchestra_research_mission.py -q
.venv/bin/python -m pytest tests/test_orchestra_claims.py tests/test_orchestra_draft_control.py tests/test_orchestra_action_planner.py -q
.venv/bin/python -m pytest tests/test_orchestra_*.py tests/test_private_smoke_safety.py -q
git diff --check
```

Preferred:

```bash
.venv/bin/python -m pytest -q
scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
```

Critic plan validation is required before implementation. Critic implementation validation is required before commit.

Implementation evidence captured before commit:

- initial test run failed before implementation with missing `paperorchestra.orchestra_omx`
- OMX invocation + research mission tests: passed
- claim/draft-control/action-planner tests: passed
- orchestrator-family + private-smoke safety tests: passed
- full test suite: passed
- private leakage scan against local denylist: passed with zero matches
- Critic implementation required two invariant-hardening edits, then verdict: APPROVE

## 8. Explicit non-goals

Slice J must not:

- execute OMX;
- call `omx exec`;
- record success/pass return codes;
- include executable command argv;
- treat planned evidence as proof that an OMX action ran;
- include raw private material in public evidence;
- make readiness pass merely because invocation evidence is planned.

## 9. Stop/replan triggers

Stop and replan if:

- planned evidence can be mistaken for executed evidence;
- public payload leaks raw material or executable argv;
- deprecated legacy autoresearch command string is accepted as a surface;
- readiness becomes unblocked by planned-only evidence;
- tests require actual OMX runtime.
