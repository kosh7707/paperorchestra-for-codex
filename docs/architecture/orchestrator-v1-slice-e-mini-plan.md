# Slice E mini-plan — high-level CLI/MCP/Skill orchestrator entrypoints

Status: slice implementation plan requiring Critic validation before code
Date: 2026-05-13
Branch: `orchestrator-v1-runtime`

## 1. Target result

Expose the v1 orchestrator skeleton through a small, high-level user/agent surface:

```text
orchestrate / run_until_blocked
inspect_state
continue_project
answer_human_needed
export_results
```

This slice makes the new state/action substrate reachable without requiring humans to memorize low-level commands.

## 2. Scope

### 2.1 CLI fallback

Add or extend CLI commands:

```text
paperorchestra inspect-state [--material PATH] [--json]
paperorchestra orchestrate [--material PATH] [--json]
paperorchestra continue-project [--json]
paperorchestra answer-human-needed --answer TEXT [--json]
```

For D/E skeleton, these commands may return state/action JSON or human-readable summaries. They must not run live models or real OMX yet.

### 2.2 MCP high-level tools

Expose a small v1 tool surface in `paperorchestra-mcp`:

```text
inspect_state
orchestrate
continue_project
answer_human_needed
export_results
```

Existing low-level MCP tools may remain for now, but docs/Skill should steer Codex toward the high-level tools.

MCP tests must preserve issue #5 dual-framing and attach smoke behavior.

### 2.3 Skill guidance

Update `skills/paperorchestra/SKILL.md` so a user saying:

```text
paperorchestra 어떻게 쓰는거야?
이거 쓰고 싶어
바로 써줘
```

is routed toward:

- `inspect_state` / `orchestrate`, not README dumping;
- minimal intake questions;
- material inspection;
- machine-solvable work before `human_needed`;
- refusal/block when material is insufficient.

## 3. Tests to add first

Proposed files/updates:

```text
tests/test_orchestrator_cli_entrypoints.py
tests/test_orchestrator_mcp_entrypoints.py
tests/test_paperorchestra_skill_guidance.py
```

Minimum failing tests before implementation:

1. CLI parser exposes `inspect-state`, `orchestrate`, `continue-project`, `answer-human-needed`;
2. `inspect-state --json` returns `schema_version=orchestra-state/1` and next actions;
3. `orchestrate --json` returns bounded action plan, not a live draft;
4. MCP `tools/list` contains high-level orchestrator tools;
5. MCP `inspect_state` tool returns v1 state payload;
6. MCP `export_results` tool exists and returns a bounded not-executed/export-plan response when no export is available;
7. MCP dual transport tests still pass;
8. Codex attach smoke is preserved for an existing tool and, where environment supports it, extended or documented for a high-level orchestrator tool;
9. Skill doc names high-level tools and warns not to dump README;
10. Skill doc says insufficient material blocks drafting and asks/proposes next valid steps;
11. Skill doc preserves MCP registration vs active attachment distinction.

## 4. Validation for this slice

Required before commit/push:

```bash
.venv/bin/python -m pytest \
  tests/test_orchestrator_cli_entrypoints.py \
  tests/test_orchestrator_mcp_entrypoints.py \
  tests/test_paperorchestra_skill_guidance.py \
  tests/test_mcp_server.py \
  tests/test_pre_live_check_script.py -q
.venv/bin/python -m pytest tests/test_orchestra_*.py -q
git diff --check
```

Preferred:

```bash
.venv/bin/python -m pytest -q
```

Critic implementation validation is required before commit.

## 5. Explicit non-goals

This slice must not:

- remove legacy low-level CLI/MCP commands yet;
- run live generation/search/OMX;
- implement full answer-human-needed repair;
- run private final smoke;
- change MCP framing behavior except preserving tests;
- weaken or remove Codex attach-smoke diagnostics; if high-level attach smoke cannot run in the environment, record an explicit blocker/reason;
- hard-code private/domain-specific use cases.

## 6. Stop/replan triggers

Stop and replan if:

- high-level tools bypass `OrchestraState`;
- CLI/MCP says a draft was produced when only an action plan was returned;
- Skill doc routes missing citations/material to the human instead of machine-solvable work;
- MCP dual-framing/attach diagnostics regress;
- skill guidance reintroduces README dumping as the default first-use response.
