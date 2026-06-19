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

## Preferred execution

Prefer the MCP tool when attached:

```text
authoring_round(cwd=..., citation_evidence_mode="web", require_web_research=true when the user expects live search)
```

CLI fallback:

```bash
paperorchestra authoring-round \
  --citation-evidence-mode web \
  --require-web-research \
  --require-live-critic
```

Use `--skip-literature`, `--skip-critic`, or `--citation-evidence-mode heuristic` only for explicit local smoke tests or when the user accepts non-live evidence.

## Round recipe

1. Start with `$paperorchestra-status` and identify the current session/materials.
2. Check for `paper-plan.md` with an author-approval marker such as `<!-- paperorchestra:plan-approved -->`. If missing, route to `$paperorchestra-plan` unless the user explicitly bypassed planning.
3. Run one `authoring_round` so pre-draft literature/positioning happens before manuscript writing.
4. If TeX is configured, compile in the round; otherwise record compile as skipped.
5. Inspect `authoring-round.manifest.json`, `positioning_brief.md`, `paper.full.tex`, `citation_support_review.json`, and `revision_suggestions.json`.
6. Route to `$paperorchestra-quality-gate` only after the round has real review artifacts or the user asks for a gate.

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
