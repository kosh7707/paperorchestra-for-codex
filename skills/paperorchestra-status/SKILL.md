---
name: paperorchestra-status
description: Inspect PaperOrchestra state and recommend the next safe workflow. Use when the user asks what materials are ready, what round should run next, whether artifacts are stale, whether live review or quality gate is appropriate, or what human decision is blocking progress.
---

# PaperOrchestra Status

## Invocation contract

Before executing any `$skill`, `omx`, `codex`, MCP, or PaperOrchestra CLI action from this skill, read `../paperorchestra/references/invocation-contract.md` and follow it. Required companion skills must be invoked, not merely recommended.

Use this as the first operational skill before expensive or state-changing work. It is read-only except for optional evidence/status exports requested by the user.

## Inspect

Prefer MCP `inspect_state` when attached. CLI fallback:

```bash
paperorchestra status --json
paperorchestra environment
```

Also inspect nearby artifacts when present: `.paper-orchestra/`, `paper-plan.md` approval state, `paper-skeleton.md` provenance/staleness, `paper.full.tex`, compiled PDF, page renders/contact sheets, figure assets, figure specs, caption drafts, `plot_manifest.json`, `plot_assets.json`, `plot_captions.json`, `figure-placement-review.json`, `page-layout-review.json`, `visual_repair_brief.json`, `visual_repair_candidate.json`, `figure_gate.report.json`, `citation_map.json`, `references.bib`, `citation_support_review.json`, `quality-eval.json`, `quality-gate.report.json`, `qa-loop.plan.json`, compile reports, and named round directories.

For a planned or drafted manuscript, report plan/skeleton availability as `approved / approved legacy / unapproved / stale / missing / not applicable` for `paper-plan.md` and `present / missing / stale / not applicable` for `paper-skeleton.md`. Do not surface internal contract hashes in user-facing summaries; they are machine fingerprints for staleness checks. A stale or missing skeleton should not override an approved plan; recommend regeneration or `$paperorchestra-plan` only when the approved contract itself is stale or insufficient.

For a figure-bearing manuscript, report figure artifact availability as `present / missing / stale / not applicable` for `plot_manifest.json`, `plot_assets.json`, `plot_captions.json`, `figure-placement-review.json`, and `figure_gate.report.json`. If an expected figure artifact is missing or stale, recommend `$paperorchestra-figure` before authoring, live-review, or quality-gate claims rely on that figure.

For a compiled manuscript, report page-visual artifact availability as `present / missing / stale / pending visual reviewer / failing / candidate ready / not applicable` for `page-layout-review.json`, rendered page contact sheets, `visual_repair_brief.json`, and `visual_repair_candidate.json`. If the compiled PDF exists but page-layout review is missing, stale, pending, or failing, recommend `$paperorchestra-visual-audit` before final quality claims.

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
  <setup needed | deep-interview required | intake recommended | plan recommended | live-review recommended | quality-gate recommended | authoring-round recommended | figure-repair recommended | visual-audit recommended | human-needed answer required | materials missing | no safe paper action available>
Reason:
Human needed:
```

Check for stale manuscript hash mismatches between current `paper.full.tex` and review/eval artifacts. Mark stale reviews clearly.

## OMX companion hints

Name both the PaperOrchestra workflow and the OMX companion when a companion would materially improve the next step. If the current user message asks to continue into the recommended next round, treat the matching companion as an invocation obligation, not a passive hint: load that companion skill and execute its state/artifact protocol before returning to the PaperOrchestra workflow, or record a concrete skip reason.

- `$deep-interview -> $paperorchestra-intake` (`$paperorchestra-intake + $deep-interview`): author intent, material boundaries, venue, experiment basis, or allowed claims are unclear. Run deep-interview first; intake only writes the handoff after the interview resolves.
- `$paperorchestra-plan + $ralplan`: manuscript structure, RQs, evidence table shape, or contribution boundaries need consensus planning.
- `$paperorchestra-authoring-round + $ultrawork`: independent pre-draft lanes can run in parallel before one bounded authoring round; invoke it when two or more such lanes are open and the user asks to proceed.
- `$paperorchestra-authoring-round + $ralph`: the user wants a persistent bounded loop over authoring, status, gate, and repair; invoke it on “continue/keep going/계속/바로 진행” after plan approval unless the user explicitly asks for a one-shot local step.
- `$ultragoal`: durable multi-story implementation or repair follow-up is needed after a plan/gate/review produces concrete work items.
- `$team + $ultragoal`: durable follow-up is also parallelizable; Team runs lanes, Ultragoal owns the ledger/checkpoints.
- `$paperorchestra-research-swarm + $ultrawork + $autoresearch`: citation/source evidence is missing, weak, stale, or machine-solvable and the gap is broad/multi-cluster; invoke it before claiming Related Work, citation support, or source-backed positioning is complete.
- `$paperorchestra-live-review + $autoresearch`: citation/source evidence is missing, weak, stale, or machine-solvable but the gap is single-lane or review-shaped; invoke it before claiming Related Work, citation support, or source-backed positioning is complete.
- `$paperorchestra-live-review + $best-practice-research`: venue/style norms or related-work positioning need external best-practice evidence.
- `$paperorchestra-quality-gate + $ultraqa`: fresh review/gate artifacts exist and adversarial final QA is the next safe action.
- `$paperorchestra-visual-audit + $visual-verdict`: compiled PDF/page screenshots need rendered-page layout, table overflow, figure readability, or cross-figure style review.
- `$paperorchestra-figure`: figure assets, captions, supported claims, or one-column/two-column placement are missing or stale.

## Recommendation rules

- Recommend `setup needed` when session/provider/compile prerequisites are missing.
- Recommend `deep-interview required` when runtime is ready but author intent, experiment basis, paper type, venue, claim boundaries, non-goals, or decision boundaries are not locked.
- Recommend `intake recommended` only when a resolved deep-interview handoff or explicit current-turn answers exist and `paper-intake.md` still needs to be written.
- Recommend `plan recommended` when intake/materials are sufficient, intake is based on a resolved deep-interview handoff or explicit current-turn answers, but no approved `paper-plan.md` exists.
- Recommend `live-review recommended` when current critic/citation evidence is mock, heuristic, local diagnostic, stale, or missing for the current manuscript hash.
- Recommend `quality-gate recommended` when live or acceptable evidence exists but no fresh quality-eval/qa-loop plan exists.
- Recommend `authoring-round recommended` after an approved plan exists and either no manuscript has been drafted yet, or review/gate evidence identifies machine-actionable manuscript improvements.
- Recommend `figure-repair recommended` for a figure-bearing manuscript when figure assets, captions, supported claims, placement, or expected figure artifacts are missing or stale; route to `$paperorchestra-figure`.
- Recommend `visual-audit recommended` when a compiled PDF exists but rendered-page visual review/contact sheets are missing, stale, pending visual review, or contain machine-actionable visual findings; route to `$paperorchestra-visual-audit`.
- Recommend `human-needed answer required` for `human_needed` plans; list exactly the decisions required.
- Recommend `materials missing` when factual paper drafting would require inventing claims, citations, figures, or results.

Do not run expensive live review or edit manuscripts from this skill unless the user separately asks for that workflow.
