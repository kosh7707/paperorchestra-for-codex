---
name: paperorchestra-authoring-round
description: Run one bounded PaperOrchestra manuscript authoring round. Use for first drafts or revision rounds after an author-approved paper plan; the round performs prior-work positioning before drafting and critic/citation review after drafting.
---

# PaperOrchestra Authoring Round

## Invocation contract

Before executing any `$skill`, `omx`, `codex`, MCP, or PaperOrchestra CLI action from this skill, read `../paperorchestra/references/invocation-contract.md` and follow it. Required companion skills must be invoked, not merely recommended.

Use this for one manuscript round, not for indefinite autonomous writing. For new papers, require an approved `paper-plan.md` or an explicit user instruction to bypass the planning gate.

Plan approval must be hash-bound when the engine supports it: prefer MCP `approve_plan` or verified `paperorchestra approve-plan` so the approval is stored as a hidden approval record beside the session artifacts.

## Core contract

A first-draft round is not “just write TeX.” It should create an auditable chain:

```text
    approved paper-plan.md -> outline -> narrative/claim/citation planning -> derived paper-skeleton.md -> prior-work/search seed -> positioning brief -> manuscript draft -> compile if available -> rendered-page visual audit if PDF exists -> critic/section/citation reviews -> revision suggestions -> manifest
```

For revision rounds, keep the same artifact chain but scope writing with `only_sections` when possible.

`paper-skeleton.md` is a derived execution projection, not a second approval source. It may guide paragraph-level moves, claim/evidence/citation refs, and section-specific exclusions, but it must not introduce new major claims, increase claim strength, or override the approved `paper-plan.md`.

The approved plan also owns the heading topology. Authoring rounds may add, remove,
split, or merge headings when the argument needs it, but must not create headings as
a substitute for deeper prose. Page-budget expansion means strengthening the existing
argument before changing the section structure.

## Academic writing doctrine

Read `../paperorchestra/references/academic-writing.md` before first-draft writing or substantial rewrites. A draft must advance the paper arc:

```text
Phenomenon → Gap → Contribution → Evidence → Boundary → Implication
```

Before writing prose, establish each target section's paragraph-level rhetorical job. While drafting, enforce the Sentence Intent Principle: every sentence must do local work at its exact position. Strong claims need claim-evidence-boundary discipline: evidence, citation support, or caveat.

Before adding, deleting, splitting, or renaming headings, run the section topology
necessity test from the academic-writing reference. Keep the change only when the
heading marks a real rhetorical boundary that cannot be carried as a paragraph,
table, figure caption, or transition inside an existing section. When the draft is
fragmented, merge first and then deepen the surviving sections.

## OMX companion routing

Use one PaperOrchestra authoring round as the bounded paper-writing action, then compose OMX skills around it through the gate below.

### Mandatory companion preflight

Before drafting prose or creating a local/manual authoring fallback, evaluate and record these companion decisions:

| Trigger | Required action before drafting |
| --- | --- |
| User says “continue”, “keep going”, “바로 진행”, “계속”, or otherwise asks the system to carry a bounded sequence forward | Invoke `$ralph` as the single-owner supervision loop for status → one authoring round → status/readback → next blocker/repair. Do not silently do a manual one-shot draft unless the user explicitly asks to avoid persistence. |
| Two or more independent pre-draft lanes are open (`two or more independent pre-draft lanes`), e.g. broad material inventory, prior-work/search seed, figure/table planning, section-structure benchmarking, claim-map/skeleton refresh | Invoke `$ultrawork` first so those lanes are planned/executed in parallel or explicitly ruled out with evidence. |
| Introduction, Related Work, positioning, citation-bearing claims, bibliography, or source-backed evidence will be created/rewritten/validated, and the current citation/source evidence is missing, weak, stale, mock/heuristic/local-only, or not current for the manuscript/plan state; the gap is broad/multi-cluster citation/source work | Invoke `$paperorchestra-research-swarm` before drafting prose so `$ultrawork`/`$team` can run parallel web lanes and `$autoresearch` can validate completion. Local `citation_map.json`/`references.bib` presence alone is not enough. |
| Introduction, Related Work, positioning, citation-bearing claims, bibliography, or source-backed evidence will be created/rewritten/validated, and the current citation/source evidence is missing, weak, stale, mock/heuristic/local-only, or not current for the manuscript/plan state; the gap is a single bounded source task | Invoke `$autoresearch` or `$paperorchestra-live-review` + `$autoresearch` before finalizing Introduction/Related Work/citation claims. If live/source research is unavailable, block citation claims or write only non-authoritative scaffolding instead of replacing `$autoresearch` with invented TODO prose. |
| Venue/style norms or comparable-paper structure are a live concern | Invoke `$best-practice-research` before locking prose shape. |

If a required companion cannot run because OMX runtime, credentials, provider configuration, or a validator is unavailable, stop with a PaperOrchestra blocker or create only clearly marked non-authoritative scaffolding. The final card must list the companion decision and evidence; “recommended next” is not enough for a trigger that was present in the current turn.

### Citation/source evidence gate

Before drafting prose, rewriting, or finalizing any Introduction, Related Work, positioning, citation-bearing, or source-backed claim, inspect the current workspace for `prior_work_seed.json`, `candidate_papers.json`, `citation_registry.json`, `citation_map.json`, `references.bib`, `citation_support_review.json`, `research-swarm.manifest.json`, and `$autoresearch` validator `result.json`. Check whether those artifacts are current for the active `paper-plan.md` and current manuscript hash when a draft exists.

Operational shorthand: when Related Work, citation candidates, bibliography, or source-backed evidence are missing, weak, stale, mock/heuristic/local-only, or not current, the citation/source evidence gate fails and the required research companion must run before manuscript prose.

Treat the gate as failing when source evidence is absent, weak, stale, heuristic/mock/local-only, candidate-only without claim-support notes, outside the active PaperOrchestra workspace, or represented only by bibliography/citation-map files without a fresh research/review/validator artifact. A failing broad or multi-cluster gate requires `$paperorchestra-research-swarm` before prose. A failing single-lane gate requires `$autoresearch` or `$paperorchestra-live-review` + `$autoresearch` before finalizing claims. If the user explicitly asks for a one-shot local scaffold, keep citation-bearing prose visibly provisional and record the skipped gate plus reason in the round artifacts and final card.

Companion usage by workflow:

- `$ultrawork`: split independent pre-draft lanes before the round when materials are large or broad, e.g. prior-work search, paper-structure benchmarking, material inventory, and figure/table planning.
- `$paperorchestra-research-swarm`: run before manuscript prose when broad/multi-cluster citation/source gaps, missing/weak/stale/local-only `prior_work_seed.json`, `candidate_papers.json`, `citation_registry.json`, `citation_map.json`, `references.bib`, or missing validator/review artifacts require parallel web/source lanes. It must invoke `$ultrawork` or `$team` for subagent lanes and `$autoresearch` for the validator gate.
- `$autoresearch`: run when a single bounded Related Work, citation candidate, or source-backed evidence task can be found by machine research, when live/source evidence for citation-bearing claims is missing/weak/stale, or as the validator gate inside `$paperorchestra-research-swarm`.
- `$best-practice-research`: use for venue/style conventions, section-shape norms, and positioning patterns from comparable papers before locking prose.
- `$ultragoal`: use for durable implementation/repair follow-up that must survive multiple stories; do not use it to bypass the bounded authoring round.
- `$team`: use with `$ultragoal` only when a durable implementation/repair plan has separable lanes; PaperOrchestra still owns manuscript artifacts.
- `$ralph`: supervise a persistent but bounded sequence such as status → one authoring round → quality gate → one repair step when the user asks to “keep going.”
- `$ultraqa`: use after the draft and review artifacts exist when the user asks for adversarial readiness checks.
- `$paperorchestra-visual-audit`: use after compile or when the draft has tables/figures whose rendered readability, one-column/two-column layout, or cross-figure style cannot be judged from TeX alone.

Do not let companion skills bypass the plan gate or invent missing evidence. They prepare or verify the round; PaperOrchestra still writes and records the manuscript artifacts.

## Preferred execution

Prefer the MCP tool when attached. For live/web first-draft rounds, and for any revision round that touches Introduction, Related Work, positioning, citation-bearing claims, or source-backed evidence, run it as a background job so Codex MCP clients do not hit their `tools/call` timeout while the provider is still working:

```text
authoring_round(
  cwd=...,
  citation_evidence_mode="web",
  require_web_research=true,
  require_live_critic=true,
  background=true
)
```

If `background` is omitted, the MCP tool automatically backgrounds rounds that request `require_web_research` or `require_live_critic`. Poll `paperorchestra status --json`, tail the returned stderr log, and read the returned stdout JSON when the job exits. If a job id is returned or discoverable, also poll `paperorchestra job-status --job-id <id>` / `run-status --job-id <id>` until terminal before claiming the round completed.

CLI staged fallback:

For MCP/source-checkout execution, `authoring_round` may delegate to a source-only `authoring-round` surface only after `python -m paperorchestra.cli authoring-round --help` succeeds. For installed CLI fallback, do not assume `paperorchestra authoring-round` exists; first run `paperorchestra authoring-round --help`. If it succeeds, prefer the bounded round command:

```bash
paperorchestra authoring-round --provider shell --provider-command "$PAPERO_MODEL_CMD" --citation-evidence-mode web --require-web-research --require-live-critic
```

If `authoring-round` is unavailable but the selected CLI surface verifies the staged commands with `--help`, preserve the closest available artifact chain:

```bash
paperorchestra research-prior-work --provider shell --provider-command "$PAPERO_MODEL_CMD" --import
paperorchestra write-sections --provider shell --provider-command "$PAPERO_MODEL_CMD"
paperorchestra critique --provider shell --provider-command "$PAPERO_MODEL_CMD" --citation-evidence-mode web
```

Use mock providers or `--citation-evidence-mode heuristic` only for explicit local smoke tests or when the user accepts non-live evidence.

## Round recipe

1. Start with `$paperorchestra-status` and identify the current session/materials.
2. Run the Mandatory companion preflight above, including the citation/source evidence gate. Required companions must be invoked before manuscript prose, not only named in the final card.
3. Check for `paper-plan.md` approval through the plan gate. Prefer MCP `approve_plan` when attached. Use a CLI approval command only after `paperorchestra <approval-command> --help` verifies it exists; otherwise accept explicit author approval text/marker only as transitional compatibility. If approval is missing or stale, route to `$paperorchestra-plan` unless the user explicitly bypassed planning.
4. Generate or refresh `paper-skeleton.md` from the approved plan plus outline/narrative/claim/citation planning before manuscript prose when the engine supports it; if the skeleton is stale or tries to change the approved contract, route back to `$paperorchestra-plan`.
5. Inspect current heading roles and compare them to the approved plan or paper-skeleton. For revision/expansion rounds, default to paragraph-level expansion inside existing headings. If adding, splitting, or keeping a heading is proposed, write the topology necessity test; if it cannot justify a real rhetorical boundary, merge the content into an existing heading instead.
6. If a figure-dependent section needs a pipeline, architecture, taxonomy, teaser, result-summary, case-study, threat-model, or visual-abstract figure before prose can be coherent, route to `$paperorchestra-figure` before finalizing that section.
7. Run one `authoring_round` so pre-draft literature/positioning happens before manuscript writing.
8. If TeX is configured, compile in the round; otherwise record compile as skipped.
9. If a compiled PDF exists, route to `$paperorchestra-visual-audit`, or run a visual-audit command only after the current CLI/source surface verifies it with `--help`, so page screenshots/contact sheets are available before quality-gate claims about layout or visual evidence.
10. If the MCP/source authoring-round returns `mode=background`, poll/tail the returned job paths until the underlying CLI finishes; then run `paperorchestra status --json` and inspect `authoring-round.manifest.json`, `paper-skeleton.md` when produced, `positioning_brief.md`, `paper.full.tex`, `page-layout-review.json` when compiled, `citation_support_review.json`, and `revision_suggestions.json`. In installed staged fallback mode, `authoring-round.manifest.json` may not exist; inspect the stage artifacts actually produced by each command.
11. Route to `$paperorchestra-quality-gate` only after the round has real review artifacts or the user asks for a gate.

## Edit boundaries

- Do not invent results, citations, figures, or metrics.
- Do not convert unapproved plans into manuscript prose unless the user explicitly says to proceed.
- For first drafts and any revision touching Introduction, Related Work, positioning, citation-bearing claims, or source-backed evidence, use web/source research and a fresh validator/review artifact when machine-solvable; if unavailable, block or clearly mark scaffolding as non-authoritative.
- For revision rounds, prefer section-scoped edits over whole-paper rewrites.
- For page-budget expansion, prefer paragraph/table/figure/case depth inside existing headings before changing section structure.
- Do not add, split, or retain headings that fail the topology necessity test.
- Keep all artifacts in the round directory.
- Report compile/validate status after the edit.

## Final card

```text
Round directory:
Plan gate:
Prior-work/search:
Citation/source evidence gate:
Positioning brief:
Draft:
Critic/citation review:
Compile/validate:
Visual audit:
Revision suggestions:
Heading topology changes:
Remaining risks:
Next recommended skill:
```
