---
name: paperorchestra
description: Route PaperOrchestra paper-writing requests to the right explicit workflow skill. Use for first use, ambiguous “how do I use this?”, material inspection, draft generation requests, or when deciding between status, setup, live review, quality gate, and authoring round workflows.
---

# PaperOrchestra Router

Use this skill as the thin front door for the packaged Codex/OMX paper-writing engine. Do not dump README. Inspect state, choose the narrowest operational skill, and preserve the v1-alpha safety boundary.

## Safety posture

PaperOrchestra is **v1-alpha**. A successful run is an auditable draft/evidence result, **not submission-ready** approval. Known limitations remain around citation/claim quality, figure finalization, and operator repair convergence. Never convert `BLOCK`, `not_ready`, `human_needed`, warnings, or a diagnostic artifact into false readiness.

If there is insufficient material, that blocks drafting. Do not fabricate claims, citations, figures, or results. Ask for a material upload/path or route to `$paperorchestra-status` instead. For “바로 써줘”, reject unsafe drafting when factual materials are missing.

## Route by intent

- `$paperorchestra-status`: answer “what is ready?”, “what changed?”, “which round next?”, stale artifact, trust-tier, and human-needed questions.
- `$paperorchestra-setup`: verify install/session/provider/compile readiness before a real paper loop.
- `$paperorchestra-live-review`: run a real live/model/web critic lane and report trust tiers without silently using mock/heuristic paths.
- `$paperorchestra-quality-gate`: run bounded validation/quality/QA state transitions and stop on `human_needed`, `failed`, or `ready_for_human_finalization`.
- `$paperorchestra-authoring-round`: perform one manuscript-improvement round after status/review/gate evidence is available.

Default order for unclear requests: `$paperorchestra-status` → recommended next skill.

## High-level orchestrator surface

Prefer high-level MCP tools when attached; otherwise use CLI fallback and say MCP active attachment is unavailable.

- `inspect_state`: inspect current session/material state and next valid actions.
- `orchestrate`: bounded v1 orchestrator. With `execute_local=true`, it performs **one deterministic local step** only; this is **not a full pipeline** and not a full paper run.
- `answer_human_needed`: record author judgment only when the engine explicitly asks.
- `export_current` / `export-current`: copy final TeX/Bib/PDF/session outputs.

When using `orchestrate`, prefer `write_evidence=true`. Report `Execution status`, action taken, adapter, reason, and next action. Evidence bundles are diagnostic artifacts, not readiness passes.

If the next action is `start_autoresearch` / `$autoresearch`, explain that remaining machine-solvable citation/search work should be handled by the engine/research surface; do not ask the user to do machine-solvable citation/search homework manually.

## MCP attachment boundary

`codex mcp list` proves registration, not active attachment. `paperorchestra doctor` proves stdio server health. Visible `mcp__paperorchestra__...` tools in a fresh Codex session prove active attachment. If active attachment is absent, use CLI fallback.

## Minimal CLI fallback map

```bash
paperorchestra status --json
paperorchestra research-prior-work --provider mock --output prior_work_seed.json --import
paperorchestra import-prior-work --seed-file prior_work_seed.json --source codex_web_seed
paperorchestra critique --provider mock --source-paper ./main.tex
paperorchestra quality-gate --no-fail-on-block
paperorchestra qa-loop --quality-mode claim_safe
paperorchestra environment
```


Core MCP tools: `status`, `research_prior_work`, `critique`, `write_sections`, `quality_gate`, `qa_loop`, `qa_loop_step`, `ralph_start`, and `export_current`. Prefer explicit workflow skills for sequencing.

Keep specialized command sequencing in the explicit workflow skills, not here.
