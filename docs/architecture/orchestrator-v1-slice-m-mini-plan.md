# Slice M mini-plan — MCP evidence bundle persistence for high-level orchestrator tools

Status: implemented and Critic-approved
Date: 2026-05-13
Branch: `orchestrator-v1-runtime`

## 1. Target result

Slice L made public-safe orchestrator evidence bundles available through the CLI:

```bash
paperorchestra orchestrate --write-evidence --json
```

Slice M exposes the same bounded persistence through the high-level MCP surface so Codex/OMX users do not need to fall back to shell commands just to preserve evidence:

```text
mcp orchestrate(write_evidence=true, evidence_output=optional_workspace_dir)
-> bounded_plan_only payload
-> evidence_bundle manifest path
```

This remains a deterministic persistence surface only. It must not run live model/search/OMX work or mark evidence as validated.

## 2. Scope

Extend:

```text
paperorchestra/mcp_server.py
tests/test_orchestrator_mcp_entrypoints.py
```

MCP tool schema changes:

```text
orchestrate:
  write_evidence: boolean
  evidence_output: string

continue_project:
  write_evidence: boolean
  evidence_output: string
```

Both tools should return the same `evidence_bundle` summary used by the CLI when requested.

## 3. Required behavior

- default behavior remains unchanged when `write_evidence` is absent/false;
- when `write_evidence=true`, write a public-safe bundle through `write_orchestrator_evidence_bundle`;
- `evidence_output` must remain workspace-contained by the Slice L writer;
- outside-workspace output should be reported as MCP `isError=true` via the existing tool-call exception handling;
- tool output may include absolute convenience paths, but bundle manifest content must remain relative/public-safe;
- writing the bundle must not change readiness, drafting permission, or execution mode.

## 4. Tests to add first

Update `tests/test_orchestrator_mcp_entrypoints.py` before implementation:

1. MCP `orchestrate` schema exposes `write_evidence` and `evidence_output`;
2. MCP `continue_project` schema exposes `write_evidence` and `evidence_output`;
3. MCP `orchestrate` with `write_evidence=true` writes a bundle and reports a manifest path;
4. the returned state remains `bounded_plan_only` and does not include `paper_full_tex`;
5. MCP `continue_project` with `write_evidence=true` writes a bundle;
6. outside-workspace `evidence_output` through `tools/call` returns `isError=true`;
7. written bundle JSON does not include the absolute workspace path.

## 5. Validation for this slice

Required before commit/push:

```bash
.venv/bin/python -m pytest tests/test_orchestrator_mcp_entrypoints.py tests/test_mcp_server.py -q
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
.venv/bin/python -m pytest tests/test_orchestrator_mcp_entrypoints.py tests/test_mcp_server.py -q
# 11 passed

.venv/bin/python -m pytest tests/test_orchestra_evidence_bundle.py tests/test_orchestrator_cli_entrypoints.py -q
# 8 passed

.venv/bin/python -m pytest tests/test_orchestra_*.py tests/test_private_smoke_safety.py -q
# 91 passed, 8 subtests passed

.venv/bin/python -m pytest -q
# 793 passed, 113 subtests passed

scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
# status ok, scanned_file_count=188, match_count=0

git diff --check
# clean
```

Critic implementation validation: APPROVE.

## 6. Explicit non-goals

Slice M must not:

- add a new standalone MCP tool unless existing high-level tools prove insufficient;
- execute research, OMX, model, compile, or export work;
- weaken MCP dual-framing behavior from issue #5;
- write private/raw material by default;
- turn bundle persistence into a readiness gate/pass condition;
- hard-code private/domain-specific material.

## 7. Stop/replan triggers

Stop and replan if:

- MCP `orchestrate` changes default behavior;
- bundle output can escape the workspace;
- bundle JSON contains the absolute workspace path;
- MCP errors become silent success payloads;
- tests require private material or live providers;
- MCP framing/attach-smoke tests regress.
