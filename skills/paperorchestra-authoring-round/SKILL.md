---
name: paperorchestra-authoring-round
description: Run one bounded PaperOrchestra manuscript authoring round. Use for first drafts or revision rounds after an author-approved paper plan; the round performs prior-work positioning before drafting and critic/citation review after drafting.
---

# PaperOrchestra Authoring Round

Use this for one manuscript round, not for indefinite autonomous writing. For new papers, require an approved `paper-plan.md` or an explicit user instruction to bypass the planning gate.

## Core contract

A first-draft round is not “just write TeX.” It should create an auditable chain:

```text
approved plan -> outline -> prior-work/search seed -> narrative/claim/citation planning -> positioning brief -> manuscript draft -> compile if available -> critic/section/citation reviews -> revision suggestions -> manifest
```

For revision rounds, keep the same artifact chain but scope writing with `only_sections` when possible.

## Academic writing doctrine

Read `../paperorchestra/references/academic-writing.md` before first-draft writing or substantial rewrites. A draft must advance the paper arc:

```text
Phenomenon → Gap → Contribution → Evidence → Boundary → Implication
```

Before writing prose, establish each target section's paragraph-level rhetorical job. While drafting, enforce the Sentence Intent Principle: every sentence must do local work at its exact position. Strong claims need claim-evidence-boundary discipline: evidence, citation support, or caveat.

## OMX companion routing

Use one PaperOrchestra authoring round as the bounded paper-writing action, then compose OMX skills around it when useful:

- `$ultrawork`: split independent pre-draft lanes before the round when materials are large or broad, e.g. prior-work search, paper-structure benchmarking, material inventory, and figure/table planning.
- `$autoresearch`: run or recommend when Related Work, citation candidates, or source-backed evidence are missing and can be found by machine research.
- `$best-practice-research`: use for venue/style conventions, section-shape norms, and positioning patterns from comparable papers before locking prose.
- `$ralph`: supervise a persistent but bounded sequence such as status → one authoring round → quality gate → one repair step when the user asks to “keep going.”
- `$ultraqa`: use after the draft and review artifacts exist when the user asks for adversarial readiness checks.

Do not let companion skills bypass the plan gate or invent missing evidence. They prepare or verify the round; PaperOrchestra still writes and records the manuscript artifacts.

## Preferred execution

Prefer the MCP tool when attached. For live/web first-draft rounds, run it as a background job so Codex MCP clients do not hit their `tools/call` timeout while the provider is still working:

```text
authoring_round(
  cwd=...,
  citation_evidence_mode="web",
  require_web_research=true,
  require_live_critic=true,
  background=true
)
```

If `background` is omitted, the MCP tool automatically backgrounds rounds that request `require_web_research` or `require_live_critic`. Poll `paperorchestra status --json`, tail the returned stderr log, and read the returned stdout JSON when the job exits.

CLI staged fallback:

For MCP/source-checkout execution, `authoring_round` may delegate to `python -m paperorchestra.cli authoring-round`. For installed CLI fallback, do not assume `paperorchestra authoring-round` exists; first run `paperorchestra authoring-round --help`. If it fails, use the staged fallback and preserve the closest available artifact chain:

```bash
paperorchestra research-prior-work --provider shell --provider-command "$PAPERO_MODEL_CMD" --import
paperorchestra plan-narrative --provider shell --provider-command "$PAPERO_MODEL_CMD"
paperorchestra write-sections --provider shell --provider-command "$PAPERO_MODEL_CMD"
paperorchestra critique --provider shell --provider-command "$PAPERO_MODEL_CMD" --citation-evidence-mode web
```

Use mock providers or `--citation-evidence-mode heuristic` only for explicit local smoke tests or when the user accepts non-live evidence.

## Round recipe

1. Start with `$paperorchestra-status` and identify the current session/materials.
2. Check for `paper-plan.md` with an author-approval marker such as `<!-- paperorchestra:plan-approved -->`. If missing, route to `$paperorchestra-plan` unless the user explicitly bypassed planning.
3. If a figure-dependent section needs a pipeline, architecture, taxonomy, teaser, result-summary, case-study, threat-model, or visual-abstract figure before prose can be coherent, route to `$paperorchestra-figure` before finalizing that section.
4. Run one `authoring_round` so pre-draft literature/positioning happens before manuscript writing.
5. If TeX is configured, compile in the round; otherwise record compile as skipped.
6. If the MCP/source authoring-round returns `mode=background`, poll/tail the returned job paths until the underlying CLI finishes; then inspect `authoring-round.manifest.json`, `positioning_brief.md`, `paper.full.tex`, `citation_support_review.json`, and `revision_suggestions.json`. In installed staged fallback mode, `authoring-round.manifest.json` may not exist; inspect the stage artifacts actually produced by each command.
7. Route to `$paperorchestra-quality-gate` only after the round has real review artifacts or the user asks for a gate.

## Edit boundaries

- Do not invent results, citations, figures, or metrics.
- Do not convert unapproved plans into manuscript prose unless the user explicitly says to proceed.
- For first drafts, use web/source research for Related Work and positioning when available.
- For revision rounds, prefer section-scoped edits over whole-paper rewrites.
- Keep all artifacts in the round directory.
- Report compile/validate status after the edit.

## Final card

```text
Round directory:
Plan gate:
Prior-work/search:
Positioning brief:
Draft:
Critic/citation review:
Compile/validate:
Revision suggestions:
Remaining risks:
Next recommended skill:
```
