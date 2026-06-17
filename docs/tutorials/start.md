# Start from a fresh checkout

Scope: first-use tutorial for safe setup, stale command avoidance, and first status checks. This page does not run live model/search, OMX-native writing, claim-safe QA, or full repository CI.

## 1. Install

Use the root installer. It hides the venv/package/skill/MCP ceremony behind one command after clone:

```bash
git clone https://github.com/kosh7707/paperorchestra-for-codex.git
cd paperorchestra-for-codex && ./install.sh
```

The installer creates `.venv`, installs the checkout, installs bundled skills, registers the Codex MCP server, prepares the shell-provider environment, and runs `omx setup` when available. Restart Codex/OMX afterwards so the MCP tool list is refreshed.

If you suspect a stale global `paperorchestra` executable is shadowing the checkout, inspect `package_context`:

```bash
.venv/bin/paperorchestra doctor
.venv/bin/paperorchestra environment --summary
```

`package_context` should point at this checkout. If it points elsewhere, use the repo-local `.venv/bin/paperorchestra` path or fix your shell `PATH`.

## 2. Ask the implementation for the current first-use guide

```bash
.venv/bin/paperorchestra first-use --intent setup
.venv/bin/paperorchestra first-use --intent how_to_use
.venv/bin/paperorchestra status --json
```

`paperorchestra environment --summary` is a compact readiness card. Use `ENVIRONMENT.md` for the full setup sheet.

## 3. Keep MCP attachment distinct from MCP registration

The installer registers MCP. Registration is not active-session attachment: restart Codex completely and open a new session before expecting `mcp__paperorchestra__...` tools. If raw MCP smoke passes but the tools are absent, use the CLI fallback and report an attachment/tool-injection issue rather than pretending MCP is active.

Useful checks when debugging setup:

```bash
scripts/smoke-paperorchestra-mcp.py --transport newline --json
scripts/smoke-codex-mcp-attach.sh
```

## 4. Stop before live work

At this point you have setup evidence, not a generated paper. Continue with the explicit PaperOrchestra skills for status, setup, live review, quality gate, or authoring rounds.
