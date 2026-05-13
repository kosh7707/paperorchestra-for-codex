# Slice N mini-plan — first-user guidance and MCP smoke for evidence persistence

Status: implemented and Critic-approved
Date: 2026-05-13
Branch: `orchestrator-v1-runtime`

## 1. Target result

Slice M made high-level MCP tools able to persist public-safe orchestrator evidence. Slice N makes that capability discoverable and smoke-testable:

```text
Skill guidance -> prefer high-level MCP orchestrate(write_evidence=true)
MCP smoke -> optional evidence probe verifies tools/call can write a bundle
Docs/tests -> explain this is MCP server health, not active Codex attachment
```

The goal is to reduce first-user confusion without changing default smoke side effects.

## 2. Scope

Extend:

```text
skills/paperorchestra/SKILL.md
paperorchestra/mcp_smoke.py
scripts/smoke-paperorchestra-mcp.py
tests/test_paperorchestra_skill_guidance.py
tests/test_pre_live_check_script.py
README.md
ENVIRONMENT.md
```

## 3. Required behavior

- skill guidance should say first-use MCP orchestration should request evidence persistence when available;
- skill guidance must still say MCP smoke proves server health, not active Codex namespace injection;
- MCP smoke default behavior must remain read-only/minimal and avoid writing bundles unless explicitly requested;
- add an opt-in smoke flag such as `--probe-evidence-bundle`;
- when enabled, smoke should call MCP `orchestrate` with `write_evidence=true` in the smoke cwd and verify:
  - `execution=bounded_plan_only`;
  - `evidence_bundle.manifest_path` exists;
  - no `paper_full_tex` appears;
  - the written bundle JSON does not contain the absolute smoke cwd path;
- smoke report should separate:
  - server health;
  - optional evidence bundle probe;
  - active Codex session attachment still not checked.

## 4. Tests to add first

Update tests before implementation:

1. skill doc mentions `write_evidence` / evidence bundle for high-level orchestrator use;
2. skill doc still preserves registration-vs-active-attachment distinction;
3. smoke script help exposes `--probe-evidence-bundle`;
4. `build_mcp_smoke_report(..., probe_evidence_bundle=True)` reports an evidence probe with `ok=true`;
5. evidence probe output is absent/unchecked by default;
6. evidence probe validates no absolute cwd path in bundle JSON;
7. smoke report remains `status=ok` when normal health passes and optional probe passes;
8. transport framing tests continue to pass.

## 5. Validation for this slice

Required before commit/push:

```bash
.venv/bin/python -m pytest tests/test_pre_live_check_script.py tests/test_paperorchestra_skill_guidance.py tests/test_orchestrator_mcp_entrypoints.py tests/test_mcp_server.py -q
.venv/bin/python -m pytest tests/test_orchestra_evidence_bundle.py tests/test_orchestrator_cli_entrypoints.py -q
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
.venv/bin/python -m pytest tests/test_pre_live_check_script.py tests/test_paperorchestra_skill_guidance.py tests/test_orchestrator_mcp_entrypoints.py tests/test_mcp_server.py -q
# 55 passed

.venv/bin/python -m pytest tests/test_orchestra_evidence_bundle.py tests/test_orchestrator_cli_entrypoints.py -q
# 8 passed

.venv/bin/python -m pytest tests/test_orchestra_*.py tests/test_private_smoke_safety.py -q
# 91 passed, 8 subtests passed

.venv/bin/python -m pytest -q
# 794 passed, 113 subtests passed

scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
# status ok, scanned_file_count=189, match_count=0

git diff --check
# clean
```

Critic implementation validation: APPROVE.

## 6. Explicit non-goals

Slice N must not:

- make smoke write files by default;
- imply MCP server smoke proves active Codex tool namespace attachment;
- execute live model/search/OMX work;
- write private/raw material by default;
- change MCP framing behavior;
- hard-code private/domain-specific use cases.

## 7. Stop/replan triggers

Stop and replan if:

- optional evidence probe changes default smoke status semantics unexpectedly;
- bundle path containment is weakened;
- docs conflate registration, server health, and active session attachment;
- tests require live providers, private material, or Codex active tool injection;
- default first-use guidance falls back to README dumping.
