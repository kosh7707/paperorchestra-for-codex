---
name: paperorchestra
description: Route PaperOrchestra paper-writing requests to the right explicit workflow skill. Use for first use, ambiguous paper-writing requests, material inspection, intake interviews, paper planning, draft generation requests, visual/page audit requests, or when deciding between setup, status, intake, plan, figure, visual audit, live review, quality gate, and authoring round workflows.
---

# PaperOrchestra Router

Use this skill as the thin front door for the packaged Codex/OMX paper-writing engine. Do not dump README. Inspect state, choose the narrowest operational skill, and preserve the v1 safety boundary.

## Safety posture

PaperOrchestra v1 produces auditable paper-writing artifacts; it does **not** certify submission readiness. Known limitations remain around citation/claim quality, figure finalization, and operator repair convergence. Never convert `BLOCK`, `not_ready`, `human_needed`, warnings, or a diagnostic artifact into false readiness.

If there is insufficient material, that blocks drafting. Do not fabricate claims, citations, figures, or results. Ask for a material upload/path or route to `$paperorchestra-status` instead. For “바로 써줘”, reject unsafe drafting when factual materials are missing.

## Fresh-start boundary

If the user explicitly requests a fresh start, context reset, or new paper session, do not reuse prior project paths, paper claims, venue assumptions, experiment facts, or stale `/tmp` artifacts from earlier conversation context. Treat only the current reset-scope user messages and inspected current session state as authoritative; ask for the material path again before intake or planning.

## Academic writing doctrine

When a task involves paper planning, drafting, review, or repair, use `references/academic-writing.md`. Treat every manuscript as a paper-typed claim structure, not an information dump:

```text
Phenomenon → Gap → Contribution → Evidence → Boundary → Implication
```

For sibling workflow skills, the same guide is available at `../paperorchestra/references/academic-writing.md` after installation.

## Route by intent

- `$paperorchestra-status`: answer “what is ready?”, “what changed?”, “which round next?”, stale artifact, trust-tier, and human-needed questions.
- `$paperorchestra-setup`: verify install/session/provider/compile readiness before a real paper loop.
- `$paperorchestra-intake`: interview the author and inventory materials when thesis, paper type, venue, experiment basis, or claim boundaries are not locked.
- `$paperorchestra-plan`: create or revise `paper-plan.md` v3 as the compact author-approved contract before manuscript drafting.
- `$paperorchestra-figure`: design, generate, or review pipeline, architecture, taxonomy, teaser, result-summary, case-study, threat-model, or visual-abstract figures with claim/caption/placement alignment.
- `$paperorchestra-visual-audit`: render compiled PDFs into page images/contact sheets, import visual findings, and route page-level visual/layout issues into `visual_repair_brief.json`.
- `$paperorchestra-live-review`: run a real live/model/web critic lane and report trust tiers without silently using mock/heuristic paths.
- `$paperorchestra-quality-gate`: run bounded validation/quality/QA state transitions and stop on `human_needed`, `failed`, or `ready_for_human_finalization`.
- `$paperorchestra-authoring-round`: perform one evidence-bearing first-draft or revision round after plan approval.

Default order for unclear first-use writing requests: `$paperorchestra-setup` if readiness is unknown → `$paperorchestra-status` → `$paperorchestra-intake` when materials/intent are not locked → `$paperorchestra-plan` → author approval → derived `paper-skeleton.md` when supported → `$paperorchestra-authoring-round`. The authoring round must do prior-work/search positioning before first-draft writing and critic/citation review after the draft exists.

## First-use interview gate

For a new paper request, a material path plus an output path is **not** enough to write `paper-intake.md` or `paper-plan.md`. Treat that as permission to inspect materials read-only and create a material inventory only. Then stop and ask the author for missing paper-shaping decisions.

Do not collapse `$paperorchestra-intake` and `$paperorchestra-plan` into one turn unless the user has already supplied explicit answers for paper type, target venue/format, central thesis, evidence/result maturity, placeholder policy, citation strategy, and claim boundaries. If those answers are absent or inferred only from repository docs, route to `$paperorchestra-intake` and end with concise interview questions.

Do not route directly to authoring when no approved `paper-plan.md` exists, unless the user explicitly asks to bypass planning.

## OMX companion routing

PaperOrchestra owns paper state and artifacts; OMX companion skills supply orchestration power around that state. Invoke or recommend them explicitly when their trigger condition is present:

- `$deep-interview`: broad ambiguity about thesis, claim boundaries, materials, venue, or experiment status before intake can be completed.
- `$ralplan`: section structure, RQs, evaluation design, or claim tradeoffs need consensus-style planning before author approval.
- `$ultrawork`: independent lanes can run in parallel, such as prior-work search, material inventory, section-structure benchmarking, and draft-outline synthesis.
- `$ralph`: the user wants a persistent completion loop over a bounded PaperOrchestra goal, such as authoring round → status → quality gate → repair.
- `$autoresearch`: machine-solvable citation/source discovery, bibliography expansion, or evidence verification remains.
- `$best-practice-research`: venue/style norms, common section naming, related-work positioning practice, or reviewer-expectation questions need external evidence.
- `$ultragoal`: approved implementation, engine-change, or repair plans should become durable sequential stories with `.omx/ultragoal` checkpoint evidence.
- `$team`: combine with `$ultragoal` when those approved stories have independent lanes; Team executes parallel work while Ultragoal remains the ledger owner.
- `$ultraqa`: final adversarial QA or hostile readiness checks are requested after live review and quality-gate artifacts exist.
- `$visual-verdict`: rendered page images/contact sheets need visual QA for overflow, figure readability, one-column/two-column layout, or cross-figure consistency.

Keep the explicit PaperOrchestra skill as the paper workflow owner. For example, use `$paperorchestra-authoring-round + $ultrawork` for parallel first-draft preparation, not raw parallel agents that bypass the paper session.
Use `$paperorchestra-figure` when a manuscript needs pipeline, architecture, taxonomy, teaser, result-summary, case-study, threat-model, or visual-abstract figures; figure work must stay tied to supported claims, source evidence, captions, and one-column/two-column placement.
Use `$paperorchestra-visual-audit + $visual-verdict` when the compiled PDF itself must be inspected as pages. Do not make TeX-only claims about rendered layout, table overflow, figure readability, or visual style consistency.
Use `$ultragoal` rather than raw `$ralph` for durable multi-step engine or repair work; reserve `$ralph` for explicitly requested single-owner persistence.

## High-level orchestrator surface

Prefer high-level MCP tools when attached; otherwise use CLI fallback and say MCP active attachment is unavailable.

CLI fallback assumes the installed `paperorchestra` console script. If running from a source checkout, first verify the surface with `paperorchestra <cmd> --help`; do not substitute `python -m paperorchestra.cli` unless explicitly working on the checkout implementation.

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
paperorchestra run --provider mock --verify-mode mock --runtime-mode compatibility
paperorchestra critique --provider mock --source-paper ./main.tex
paperorchestra quality-eval --quality-mode claim_safe
paperorchestra qa-loop-plan --quality-mode claim_safe
paperorchestra qa-loop-step --quality-mode claim_safe --max-iterations 1
paperorchestra environment
```


Core MCP tools: `status`, `research_prior_work`, `authoring_round`, `critique`, `visual_audit`, `write_sections`, `quality_gate`, `qa_loop`, `qa_loop_step`, `ralph_start`, and `export_current`. Prefer explicit workflow skills for sequencing.

Keep specialized command sequencing in the explicit workflow skills, not here.
