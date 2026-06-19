---
name: paperorchestra-status
description: Inspect PaperOrchestra state and recommend the next safe workflow. Use when the user asks what materials are ready, what round should run next, whether artifacts are stale, whether live review or quality gate is appropriate, or what human decision is blocking progress.
---

# PaperOrchestra Status

Use this as the first operational skill before expensive or state-changing work. It is read-only except for optional evidence/status exports requested by the user.

## Inspect

Prefer MCP `inspect_state` when attached. CLI fallback:

```bash
paperorchestra status --json
paperorchestra environment
```

Also inspect nearby artifacts when present: `.paper-orchestra/`, `paper-plan.md` approval state, `paper.full.tex`, figure assets, figure specs, caption drafts, `plot_manifest.json`, `plot_assets.json`, `plot_captions.json`, `figure-placement-review.json`, `figure_gate.report.json`, `citation_map.json`, `references.bib`, `citation_support_review.json`, `quality-eval.json`, `quality-gate.report.json`, `qa-loop.plan.json`, compile reports, and named round directories.

For a figure-bearing manuscript, report figure artifact availability as `present / missing / stale / not applicable` for `plot_manifest.json`, `plot_assets.json`, `plot_captions.json`, `figure-placement-review.json`, and `figure_gate.report.json`. If an expected figure artifact is missing or stale, recommend `$paperorchestra-figure` before authoring, live-review, or quality-gate claims rely on that figure.

## Fresh-start boundary

If the user explicitly requests a fresh start, context reset, or new paper session, do not reuse prior project paths, old `/tmp` workspaces, old manuscript assumptions, or earlier experiment facts as current truth. Report only current session/material state; if no current material is present, say so and ask for the material path again instead of inferring it.

## Status card

Report a compact status card with these headings:

```text
Materials:
  ready:
  missing:
  optional missing:
Current trust:
  critic:
  citation review:
  claim-safe live:
Latest artifacts:
  compile:
  quality gate:
  citation support:
Recommended next round:
  <setup needed | intake recommended | plan recommended | live-review recommended | quality-gate recommended | authoring-round recommended | figure-repair recommended | human-needed answer required | materials missing | no safe paper action available>
Reason:
Human needed:
```

Check for stale manuscript hash mismatches between current `paper.full.tex` and review/eval artifacts. Mark stale reviews clearly.

## OMX companion hints

Name both the PaperOrchestra workflow and the OMX companion when a companion would materially improve the next step:

- `$paperorchestra-intake + $deep-interview`: author intent, material boundaries, venue, experiment basis, or allowed claims are unclear.
- `$paperorchestra-plan + $ralplan`: manuscript structure, RQs, evidence table shape, or contribution boundaries need consensus planning.
- `$paperorchestra-authoring-round + $ultrawork`: independent pre-draft lanes can run in parallel before one bounded authoring round.
- `$paperorchestra-authoring-round + $ralph`: the user wants a persistent bounded loop over authoring, status, gate, and repair.
- `$paperorchestra-live-review + $autoresearch`: citation/source evidence is missing, weak, stale, or machine-solvable.
- `$paperorchestra-live-review + $best-practice-research`: venue/style norms or related-work positioning need external best-practice evidence.
- `$paperorchestra-quality-gate + $ultraqa`: fresh review/gate artifacts exist and adversarial final QA is the next safe action.
- `$paperorchestra-figure`: figure assets, captions, supported claims, or one-column/two-column placement are missing or stale.

## Recommendation rules

- Recommend `setup needed` when session/provider/compile prerequisites are missing.
- Recommend `intake recommended` when runtime is ready but author intent, material paths, experiment basis, paper type, venue, or claim boundaries are not locked.
- Recommend `plan recommended` when intake/materials are sufficient but no approved `paper-plan.md` exists.
- Recommend `live-review recommended` when current critic/citation evidence is mock, heuristic, local diagnostic, stale, or missing for the current manuscript hash.
- Recommend `quality-gate recommended` when live or acceptable evidence exists but no fresh quality-eval/qa-loop plan exists.
- Recommend `authoring-round recommended` after an approved plan exists and either no manuscript has been drafted yet, or review/gate evidence identifies machine-actionable manuscript improvements.
- Recommend `figure-repair recommended` for a figure-bearing manuscript when figure assets, captions, supported claims, placement, or expected figure artifacts are missing or stale; route to `$paperorchestra-figure`.
- Recommend `human-needed answer required` for `human_needed` plans; list exactly the decisions required.
- Recommend `materials missing` when factual paper drafting would require inventing claims, citations, figures, or results.

Do not run expensive live review or edit manuscripts from this skill unless the user separately asks for that workflow.
