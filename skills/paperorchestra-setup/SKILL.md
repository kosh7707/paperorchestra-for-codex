---
name: paperorchestra-setup
description: Verify the Codex/OMX paper-writing engine environment, session, provider, compile, and MCP readiness. Use for setup, preflight, S2-key questions, PAPERO_MODEL_CMD checks, MCP attachment checks, and deciding whether a run is mock, heuristic, shell-live, or claim-safe-live.
---

# PaperOrchestra Setup

Run this before live review, quality gates, or authoring rounds when environment readiness is uncertain.

## Checks

Use the narrowest available surface:

```bash
command -v paperorchestra
paperorchestra --help
paperorchestra doctor
paperorchestra environment
paperorchestra status --json
```

If repo checkout commands are being tested, compare with `python3 -m paperorchestra.cli --help` and report any command-surface mismatch. Do not silently mix installed CLI examples with source-checkout-only commands.

If MCP is expected, distinguish registration from active attachment:

```bash
codex mcp list
paperorchestra doctor
```

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
Citation evidence:
S2:
Readiness:
Next safe skill:
```

Never imply that setup success means the manuscript is submission-ready.
