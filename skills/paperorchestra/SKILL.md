---
name: paperorchestra
description: Route PaperOrchestra paper-writing requests to the right explicit workflow skill. Use for first use, ambiguous paper-writing requests, material inspection, intake interviews, paper planning, draft generation requests, visual/page audit requests, or when deciding between setup, status, intake, plan, figure, visual audit, live review, quality gate, and authoring round workflows.
---

# PaperOrchestra Router

## Invocation contract

Before executing any `$skill`, `omx`, `codex`, MCP, or PaperOrchestra CLI action from this skill, read `references/invocation-contract.md` and follow it. Required companion skills must be invoked, not merely recommended.

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
- `$paperorchestra-intake`: convert a completed `$deep-interview` author clarification plus material inventory into `paper-intake.md` when thesis, paper type, venue, experiment basis, and claim boundaries are locked.
- `$paperorchestra-plan`: create or revise `paper-plan.md` v3 as the compact author-approved contract before manuscript drafting.
- `$paperorchestra-figure`: design, generate, or review pipeline, architecture, taxonomy, teaser, result-summary, case-study, threat-model, or visual-abstract figures with claim/caption/placement alignment.
- `$paperorchestra-visual-audit`: render compiled PDFs into page images/contact sheets, import visual findings, and route page-level visual/layout issues into `visual_repair_brief.json`.
- `$paperorchestra-research-swarm`: run parallel, source-backed prior-work/citation discovery when Related Work, `citation_map.json`, `references.bib`, or evidence verification needs broad/multi-cluster web research.
- `$paperorchestra-live-review`: run a real live/model/web critic lane and report trust tiers without silently using mock/heuristic paths.
- `$paperorchestra-quality-gate`: run bounded validation/quality/QA state transitions and stop on `human_needed`, `failed`, or `ready_for_human_finalization`.
- `$paperorchestra-authoring-round`: perform one evidence-bearing first-draft or revision round after plan approval.

Default order for unclear first-use writing requests: `$paperorchestra-setup` if readiness is unknown → `$paperorchestra-status` / read-only material inventory → `$deep-interview` for author clarification → `$paperorchestra-intake` to write the intake handoff → `$paperorchestra-plan` → author approval → derived `paper-skeleton.md` when supported → `$paperorchestra-authoring-round`. The authoring round must do prior-work/search positioning before first-draft writing and critic/citation review after the draft exists.

## First-use interview gate

For a new paper request, a material path plus an output path is **not** enough to write `paper-intake.md` or `paper-plan.md`. Treat that as permission to inspect materials read-only and create a material inventory only. Then invoke `$deep-interview` with the inventory and stop on its author questions.

Do not collapse `$deep-interview`, `$paperorchestra-intake`, and `$paperorchestra-plan` into one turn unless the user has already supplied explicit answers for paper type, target venue/format, central thesis, evidence/result maturity, placeholder policy, citation strategy, and claim boundaries. If those answers are absent or inferred only from repository docs, route to `$deep-interview` first. `$paperorchestra-intake` may only write the handoff after the interview resolves or explicitly defers those decisions.

The router must not treat `$paperorchestra-intake` as a substitute for `$deep-interview`. Intake is the PaperOrchestra artifact wrapper around resolved interview answers; `$deep-interview` is the ambiguity-gating conversation before intake and plan.

## Deep-interview invocation contract

`$deep-interview` is an OMX skill, not a `paperorchestra` CLI subcommand. To invoke it, the main agent must load the installed `deep-interview` skill instructions and execute that workflow. Do not merely mention `$deep-interview` as the next recommendation.

In an attached tmux OMX runtime, a valid invocation includes:

1. read the `deep-interview` skill;
2. initialize/persist `deep-interview` mode state with `omx state write`;
3. ask each interview round through `OMX_QUESTION_RETURN_PANE=$TMUX_PANE omx question --input '<json>' --json` with `source:"deep-interview"`;
4. write a resolved handoff artifact under `.omx/specs/deep-interview-*.md` and transcript under `.omx/interviews/` before handing off to intake/plan.

If that runtime path is unavailable, ask exactly one fallback question and mark the run blocked for PaperOrchestra intake; do not write `paper-intake.md` or `paper-plan.md` from fallback questioning in the same turn.

Before `$paperorchestra-intake` or `$paperorchestra-plan`, require either:

- an explicit current user message that answers all required intake decisions; or
- a deep-interview handoff artifact path from `.omx/specs/deep-interview-*.md` plus the material inventory it was based on.

Do not route directly to authoring when no approved `paper-plan.md` exists, unless the user explicitly asks to bypass planning.

## OMX companion routing

PaperOrchestra owns paper state and artifacts; OMX companion skills supply orchestration power around that state.

### Companion invocation gate

Do not treat companion workflow names as decorative hints. If a trigger below is present in the active user request or in the current PaperOrchestra status, the main agent must either:

1. invoke the companion skill by loading its installed `SKILL.md` and executing its workflow/state protocol before continuing the PaperOrchestra step; or
2. record a concrete skip reason such as `runtime unavailable`, `no independent lanes`, `citation work not machine-solvable`, or `user requested one-shot local drafting`.

Merely naming the companion as a future recommendation is insufficient when the current turn asks to continue through the triggered work. In particular, after plan approval, user messages such as “continue”, “keep going”, “바로 진행”, or “계속” activate the bounded persistence branch: use `$ralph` around the next PaperOrchestra action unless the user explicitly asks for a one-shot, non-persistent local step.

Invoke or recommend these companions explicitly when their trigger condition is present:

- `$deep-interview`: mandatory for fresh or ambiguous paper requests before intake when thesis, claim boundaries, materials, venue, or experiment status are not already explicit.
- `$ralplan`: section structure, RQs, evaluation design, or claim tradeoffs need consensus-style planning before author approval.
- `$ultrawork`: mandatory before first-draft authoring when two or more independent pre-draft lanes are open, such as material inventory, prior-work/search seed, section-structure benchmarking, figure/table planning, and draft-outline synthesis.
- `$ralph`: mandatory when the user asks to continue/persist through a bounded PaperOrchestra sequence, such as status → authoring round → quality gate → repair, or when a previous round ended with machine-actionable blockers and the user says to keep going.
- `$paperorchestra-research-swarm`: mandatory before raw `$autoresearch` when machine-solvable citation/source discovery, bibliography expansion, or evidence verification is broad/deep, spans multiple clusters, or benefits from parallel web lanes. This skill invokes `$ultrawork`/`$team` for subagent lanes and `$autoresearch` for the validator gate.
- `$autoresearch`: mandatory as the validator-gated research loop for single-lane citation/source discovery, or as the completion gate inside `$paperorchestra-research-swarm`.
- `$best-practice-research`: venue/style norms, common section naming, related-work positioning practice, or reviewer-expectation questions need external evidence.
- `$ultragoal`: approved implementation, engine-change, or repair plans should become durable sequential stories with `.omx/ultragoal` checkpoint evidence.
- `$team`: combine with `$ultragoal` when those approved stories have independent lanes; Team executes parallel work while Ultragoal remains the ledger owner.
- `$ultraqa`: final adversarial QA or hostile readiness checks are requested after live review and quality-gate artifacts exist.
- `$visual-verdict`: rendered page images/contact sheets need visual QA for overflow, figure readability, one-column/two-column layout, or cross-figure consistency.

Keep the explicit PaperOrchestra skill as the paper workflow owner. For example, use `$paperorchestra-authoring-round + $ultrawork` for parallel first-draft preparation, not raw parallel agents that bypass the paper session.
Use `$paperorchestra-research-swarm + $ultrawork + $autoresearch` for broad prior-work/search seed generation, not ad-hoc browsing that bypasses `prior_work_seed.json`, `citation_map.json`, or `references.bib`.
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
