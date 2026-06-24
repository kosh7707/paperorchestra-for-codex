---
name: paperorchestra-setup
description: Verify the Codex/OMX paper-writing engine environment, session, provider, compile, and MCP readiness. Use for setup, preflight, S2-key questions, PAPERO_MODEL_CMD checks, MCP attachment checks, and deciding whether a run is mock, heuristic, shell-live, or claim-safe-live.
---

# PaperOrchestra Setup

## Invocation contract

Before executing any `$skill`, `omx`, `codex`, MCP, or PaperOrchestra CLI action from this skill, read `../paperorchestra/references/invocation-contract.md` and follow it. Required companion skills must be invoked, not merely recommended.

Run this before live review, quality gates, or authoring rounds when environment readiness is uncertain.

## Checks

Use the narrowest available surface:

```bash
command -v paperorchestra
command -v paperorchestra-mcp
paperorchestra --help
paperorchestra doctor
paperorchestra environment
paperorchestra status --json
```

Always include a command-surface probe for source-only/stale-install drift. The recurring setup failure is: Codex skills are updated from one checkout, but the `paperorchestra` console script on PATH imports an older editable checkout and therefore hides newer commands such as `visual-audit`.

From a repository checkout, run the bundled probe:

```bash
scripts/check-cli-surface.py --source-root "$(pwd)" --require visual-audit
```

Use strict mode when the setup verdict needs to fail closed on a stale installed console:

```bash
scripts/check-cli-surface.py --source-root "$(pwd)" --require visual-audit --strict-installed --json
```

If the probe reports `installed_mismatch` or `warning` while the source/venv command is OK, do not block the paper workflow as if the command does not exist. Use the checkout-local command surface and report the mismatch:

```bash
.venv/bin/paperorchestra visual-audit --help
PYTHONPATH="$(pwd)" python3 -m paperorchestra.cli visual-audit --help
```

Repair the installed surface by reinstalling the current checkout and putting its venv first on PATH:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
export PATH="$(pwd)/.venv/bin:$PATH"
scripts/register-codex-mcp.sh --use-local-venv
```

When running from a repository checkout, also verify the checkout-local virtualenv commands when present:

```bash
test -x .venv/bin/paperorchestra
test -x .venv/bin/paperorchestra-mcp
.venv/bin/paperorchestra --version
.venv/bin/paperorchestra doctor
```

Report a PATH/source mismatch when `command -v paperorchestra` points outside the current checkout while `.venv/bin/paperorchestra` exists, or when `paperorchestra doctor` reports a `package_context.package_root` that does not match the current checkout. Prefer the checkout-local `.venv/bin/paperorchestra` for setup evidence in that case. This is a setup warning, not a paper-readiness pass.

If repo checkout commands are being tested, compare with `python3 -m paperorchestra.cli --help` and report any command-surface mismatch. Do not silently mix installed CLI examples with source-checkout-only commands. If the source surface verifies a command and the installed console does not, either use `.venv/bin/paperorchestra <command>` or `PYTHONPATH=<checkout> python3 -m paperorchestra.cli <command>` and record the fallback in the setup card.

If MCP is expected, distinguish registration from active attachment:

```bash
codex mcp list
paperorchestra doctor
```

Do not treat `codex mcp list` `enabled` as sufficient. Inspect the PaperOrchestra doctor JSON field `paperorchestra_mcp_health` and report:

- config registration: `paperorchestra_mcp_health.config.registered`, `enabled`, and registered MCP command;
- binary health: `paperorchestra_mcp_health.binary.exists` and `resolved_command`;
- stdio server health: `paperorchestra_mcp_health.server.ok`, `initialize_ok`, `tools_list_ok`, and missing expected tools;
- active session attachment: `paperorchestra_mcp_health.active_session_attachment` plus whether `mcp__paperorchestra__...` tools are visible in this Codex session.

If the registered MCP command points to a missing path, for example a deleted checkout `.venv/bin/paperorchestra-mcp`, setup is degraded even when `codex mcp list` says `enabled`. Repair by creating/installing the checkout venv (`python3 -m venv .venv && .venv/bin/python -m pip install -e .`) and re-running `scripts/register-codex-mcp.sh --use-local-venv`, or by registering an existing `paperorchestra-mcp` command explicitly. After repair, rerun `paperorchestra doctor` or `.venv/bin/paperorchestra doctor` and verify `binary.exists=true` and `server.ok=true`. A Codex restart may still be required before active MCP tools appear.

## Classify readiness

Report one of:

- `mock`: mock provider or local checks only.
- `heuristic`: offline citation/metadata checks only.
- `shell-live`: shell provider can call a live model, but web citation trust may be absent; verify with `$paperorchestra-live-review`.
- `claim-safe-live`: live provider plus web/source citation evidence and strict gate prerequisites are ready; verify with `$paperorchestra-live-review` and `$paperorchestra-quality-gate`.

S2 API key is optional. Its absence is not fatal when web/source citation evidence or manual source artifacts are used. Do not block setup solely because S2 is unset.

## OMX companion routing

- Use `$omx-setup` or `omx doctor` when the OMX runtime itself is missing or stale.
- Recommend `$paperorchestra-status` after setup succeeds so the next paper-state action is read-only.
- Recommend `$paperorchestra-live-review` only after shell-live readiness is confirmed.
- Recommend `$paperorchestra-quality-gate` only after live review or acceptable citation evidence exists.

## Output

Return a short setup card:

```text
Session:
Provider:
Compile:
MCP:
MCP registration command:
MCP binary/server:
Active MCP attachment:
PATH/source:
CLI surface:
Citation evidence:
S2:
Readiness:
Next safe skill:
```

Never imply that setup success means the manuscript is submission-ready.
