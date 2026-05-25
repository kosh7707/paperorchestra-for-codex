# Start from a fresh checkout

Scope: first-use tutorial for safe setup, stale command avoidance, and first status checks. This page does not run live model/search, OMX-native writing, claim-safe QA, or full repository CI.

## 1. Install into a local venv

```bash
git clone https://github.com/kosh7707/paperorchestra-for-codex.git
cd paperorchestra-for-codex
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Use the venv command first because some Linux distributions enforce PEP 668 and because a stale global `paperorchestra` executable can shadow the checkout. When in doubt, prefer the repo-local module form:

```bash
python -m paperorchestra.cli --help
python -m paperorchestra.cli doctor
```

Then check `package_context` in `paperorchestra doctor`; it should point at this checkout. If it points elsewhere, fix your shell `PATH` or activate `.venv` again before continuing.

## 2. Ask the implementation for the current first-use guide

```bash
paperorchestra first-use --intent setup
paperorchestra first-use --intent how_to_use
paperorchestra environment --summary
```

`paperorchestra environment --summary` is a compact readiness card. Use `ENVIRONMENT.md` for the full setup sheet.

## 3. Keep MCP attachment distinct from MCP registration

MCP registration is not active-session attachment. After registering MCP, restart Codex completely and open a new session before expecting `mcp__paperorchestra__...` tools. If raw MCP smoke passes but the tools are absent, use the CLI fallback and report an attachment/tool-injection issue rather than pretending MCP is active.

Useful checks:

```bash
./scripts/register-codex-mcp.sh --use-local-venv --dry-run
./scripts/register-codex-mcp.sh --use-local-venv
scripts/smoke-paperorchestra-mcp.py --transport newline --json
scripts/smoke-codex-mcp-attach.sh
```

## 4. Stop before live work

At this point you have setup evidence, not a generated paper. Continue with [`mock-demo.md`](mock-demo.md) before any live model/search run.
