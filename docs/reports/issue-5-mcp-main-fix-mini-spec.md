# Issue #5 Main-Branch MCP Fix Mini-Spec

Date: 2026-05-13
Branch: `main`
Related issue: [#5 MCP registers and responds but native Codex tools may not attach to active session](https://github.com/kosh7707/paperorchestra-for-codex/issues/5)
Root-cause report: `docs/reports/issue-5-codex-mcp-framing-root-cause.md`

## Purpose

Fix only the MCP stdio transport compatibility problem on `main` before the larger v1 orchestrator branch begins.

The `main` change must make `paperorchestra-mcp` compatible with both:

1. existing `Content-Length` framed JSON-RPC messages;
2. Codex-observed newline-delimited JSON-RPC messages.

## Non-goals on `main`

Do not begin the v1 orchestrator rewrite on `main`.

Out of scope for this branch:

- `OrchestraState` / `OrchestraOrchestrator` runtime rewrite;
- B→C→D vertical-slice paper-writing work;
- scholarly scoring / multi-Critic consensus overhaul;
- broad MCP/Skill redesign beyond issue #5 compatibility;
- CCI/private final-smoke material preparation;
- team/ultrawork/autoresearch product runtime integration.

## Allowed file scope

Implementation and tests should stay within this narrow scope unless a Critic-approved blocker requires expansion:

- `paperorchestra/mcp_server.py`
- `paperorchestra/mcp_smoke.py`
- `scripts/smoke-paperorchestra-mcp.py`
- `scripts/smoke-codex-mcp-attach.sh` (new, if executable Codex attach smoke is implemented)
- `tests/test_mcp_server.py`
- `tests/test_pre_live_check_script.py` only if script/help assertions need updating
- `README.md` / `ENVIRONMENT.md` / `scripts/register-codex-mcp.sh` only for narrow MCP readiness wording
- `docs/reports/issue-5-codex-mcp-framing-root-cause.md`
- `docs/reports/issue-5-mcp-main-fix-mini-spec.md`

## Required behavior

### Dual input framing

`paperorchestra-mcp` must read:

- `Content-Length: N\r\n\r\n<json>` messages;
- one complete JSON-RPC object per newline when the first non-empty line begins with `{`.

### Mirrored output framing

`paperorchestra-mcp` must respond using the currently detected client framing mode:

- Content-Length request → Content-Length response;
- newline request → newline JSON response.

### Multi-message session compatibility

Both transports must support this sequence:

```text
initialize
notifications/initialized
tools/list
tools/call status
```

### Protocol negotiation

Codex-observed initialize requests with:

```json
"protocolVersion": "2025-06-18"
```

must receive a successful initialize response. If the implementation chooses a different protocolVersion in the response, the behavior must be documented and covered by tests.

Preferred response policy for this narrow fix:

- respond with the requested `protocolVersion` when it is in a supported set;
- keep current `2024-11-05` compatibility for older smoke clients.

## Required tests before implementation is accepted

### Unit tests

Add or expand tests so they fail on the current implementation and pass after the fix:

- newline JSON `initialize` using Codex-style `2025-06-18` succeeds;
- newline multi-message flow reaches `status` tool;
- Content-Length flow still reaches `status` tool;
- writer mirrors newline framing;
- writer mirrors Content-Length framing;
- protocol negotiation is explicit for `2025-06-18` and `2024-11-05`.

### Smoke tests

`scripts/smoke-paperorchestra-mcp.py` must support explicit transport selection:

```bash
scripts/smoke-paperorchestra-mcp.py --transport content-length --json
scripts/smoke-paperorchestra-mcp.py --transport newline --json
```

Default behavior may run both transports or remain backward-compatible, but both explicit commands must work.

### Codex attach smoke

Add an isolated attach smoke if feasible:

```bash
scripts/smoke-codex-mcp-attach.sh
```

Requirements:

- must not mutate the user's normal `~/.codex/config.toml`;
- should use a temporary `CODEX_HOME` / config where Codex supports it;
- must record Codex CLI version;
- must preserve JSONL evidence;
- pass condition is a JSONL item containing an MCP tool call with:

```json
{
  "type": "mcp_tool_call",
  "server": "paperorchestra",
  "tool": "status"
}
```

If Codex auth/model/environment prevents the attach smoke from running, record the exact blocker and keep raw transport smokes as required evidence. Do not silently skip.

### Full test run

Run:

```bash
python -m pytest -q
```

This is mandatory unless there is a documented pre-existing unrelated blocker.

### Container verification

Run a container-backed smoke when Docker/image is available.

Rules:

- container verification must include the working-tree changes or run from the post-commit tree;
- if Docker/image is unavailable, record exact `docker info` or image failure output;
- do not claim container verification passed unless it actually exercised the fixed transport.

## Acceptance checklist

The main-branch fix is complete only when all of these are true:

- root-cause report is present under `docs/reports/`;
- mini-spec is present under `docs/reports/`;
- newline transport tests pass;
- Content-Length transport tests pass;
- `scripts/smoke-paperorchestra-mcp.py --transport content-length --json` passes;
- `scripts/smoke-paperorchestra-mcp.py --transport newline --json` passes;
- full pytest passes or an exact unrelated blocker is recorded;
- Codex attach smoke passes or an exact environment blocker is recorded;
- container-backed smoke passes or an exact Docker/image blocker is recorded;
- docs/smoke messaging no longer implies raw MCP smoke proves active Codex session attachment;
- commit uses Lore Commit Protocol;
- `main` is pushed before creating `orchestrator-v1-runtime`.
