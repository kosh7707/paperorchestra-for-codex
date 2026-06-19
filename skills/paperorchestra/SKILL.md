---
name: paperorchestra
description: Route PaperOrchestra paper-writing requests to the right explicit workflow skill. Use for first use, ambiguous paper-writing requests, material inspection, intake interviews, paper planning, draft generation requests, or when deciding between setup, status, intake, plan, live review, quality gate, and authoring round workflows.
---

# PaperOrchestra Router

Use this skill as the thin front door for the packaged Codex/OMX paper-writing engine. Do not dump README. Inspect state, choose the narrowest operational skill, and preserve the v1 safety boundary.

## Safety posture

PaperOrchestra v1 produces auditable paper-writing artifacts; it does **not** certify submission readiness. Known limitations remain around citation/claim quality, figure finalization, and operator repair convergence. Never convert `BLOCK`, `not_ready`, `human_needed`, warnings, or a diagnostic artifact into false readiness.

If there is insufficient material, that blocks drafting. Do not fabricate claims, citations, figures, or results. Ask for a material upload/path or route to `$paperorchestra-status` instead. For “바로 써줘”, reject unsafe drafting when factual materials are missing.

## Route by intent

- `$paperorchestra-status`: answer “what is ready?”, “what changed?”, “which round next?”, stale artifact, trust-tier, and human-needed questions.
- `$paperorchestra-setup`: verify install/session/provider/compile readiness before a real paper loop.
- `$paperorchestra-intake`: interview the author and inventory materials when thesis, paper type, venue, experiment basis, or claim boundaries are not locked.
- `$paperorchestra-plan`: create or revise `paper-plan.md` for author approval before manuscript drafting.
- `$paperorchestra-live-review`: run a real live/model/web critic lane and report trust tiers without silently using mock/heuristic paths.
- `$paperorchestra-quality-gate`: run bounded validation/quality/QA state transitions and stop on `human_needed`, `failed`, or `ready_for_human_finalization`.
- `$paperorchestra-authoring-round`: perform one evidence-bearing first-draft or revision round after plan approval.

Default order for unclear first-use writing requests: `$paperorchestra-setup` if readiness is unknown → `$paperorchestra-status` → `$paperorchestra-intake` when materials/intent are not locked → `$paperorchestra-plan` → author approval → `$paperorchestra-authoring-round`. The authoring round must do prior-work/search positioning before first-draft writing and critic/citation review after the draft exists.

Do not route directly to authoring when no approved `paper-plan.md` exists, unless the user explicitly asks to bypass planning.

## OMX companion routing

PaperOrchestra owns paper state and artifacts; OMX companion skills supply orchestration power around that state. Invoke or recommend them explicitly when their trigger condition is present:

- `$deep-interview`: broad ambiguity about thesis, claim boundaries, materials, venue, or experiment status before intake can be completed.
- `$ralplan`: section structure, RQs, evaluation design, or claim tradeoffs need consensus-style planning before author approval.
- `$ultrawork`: independent lanes can run in parallel, such as prior-work search, material inventory, section-structure benchmarking, and draft-outline synthesis.
- `$ralph`: the user wants a persistent completion loop over a bounded PaperOrchestra goal, such as authoring round → status → quality gate → repair.
- `$autoresearch`: machine-solvable citation/source discovery, bibliography expansion, or evidence verification remains.
- `$best-practice-research`: venue/style norms, common section naming, related-work positioning practice, or reviewer-expectation questions need external evidence.
- `$ultraqa`: final adversarial QA or hostile readiness checks are requested after live review and quality-gate artifacts exist.

Keep the explicit PaperOrchestra skill as the paper workflow owner. For example, use `$paperorchestra-authoring-round + $ultrawork` for parallel first-draft preparation, not raw parallel agents that bypass the paper session.

## High-level orchestrator surface

Prefer high-level MCP tools when attached; otherwise use CLI fallback and say MCP active attachment is unavailable.

- `inspect_state`: inspect current session/material state and next valid actions.
- `orchestrate`: bounded v1 orchestrator. With `execute_local=true`, it performs **one deterministic local step** only; this is **not a full pipeline** and not a full paper run.
- Before any `run_pipeline` or `write_sections`, prefer intake/plan artifacts (`paper-intake.md`, `paper-plan.md`) for new projects. For actual first-draft work, prefer `authoring_round` over raw `write_sections` so related-work positioning and critic artifacts are produced in the same round.
- `answer_human_needed`: record author judgment only when the engine explicitly asks.
- `export_current` / `export-current`: copy final TeX/Bib/PDF/session outputs.

When using `orchestrate`, prefer `write_evidence=true`. Report `Execution status`, action taken, adapter, reason, and next action. Evidence bundles are diagnostic artifacts, not readiness passes.

If the next action is `start_autoresearch` / `$autoresearch`, explain that remaining machine-solvable citation/search work should be handled by the engine/research surface; do not ask the user to do machine-solvable citation/search homework manually.

## MCP attachment boundary

`codex mcp list` proves registration, not active attachment. `paperorchestra doctor` proves stdio server health. Visible `mcp__paperorchestra__...` tools in a fresh Codex session prove active attachment. If active attachment is absent, use CLI fallback.

## Minimal CLI fallback map

```bash
paperorchestra status --json
paperorchestra authoring-round --provider mock --citation-evidence-mode heuristic
paperorchestra critique --provider mock --source-paper ./main.tex
paperorchestra quality-gate --no-fail-on-block
paperorchestra qa-loop --quality-mode claim_safe
paperorchestra environment
```


Core MCP tools: `status`, `research_prior_work`, `authoring_round`, `critique`, `write_sections`, `quality_gate`, `qa_loop`, `qa_loop_step`, `ralph_start`, and `export_current`. Prefer explicit workflow skills for sequencing.

Keep specialized command sequencing in the explicit workflow skills, not here.
