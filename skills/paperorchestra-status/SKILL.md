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
paperorchestra environment --summary
```

Also inspect nearby artifacts when present: `.paper-orchestra/`, `paper-plan.md` approval state, `paper.full.tex`, `citation_map.json`, `references.bib`, `citation_support_review.json`, `quality-eval.json`, `qa-loop.plan.json`, compile reports, and named round directories.

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
  <setup needed | intake recommended | plan recommended | live-review recommended | quality-gate recommended | authoring-round recommended | human-needed answer required | materials missing | no safe paper action available>
Reason:
Human needed:
```

Check for stale manuscript hash mismatches between current `paper.full.tex` and review/eval artifacts. Mark stale reviews clearly.

## Recommendation rules

- Recommend `setup needed` when session/provider/compile prerequisites are missing.
- Recommend `intake recommended` when runtime is ready but author intent, material paths, experiment basis, paper type, venue, or claim boundaries are not locked.
- Recommend `plan recommended` when intake/materials are sufficient but no approved `paper-plan.md` exists.
- Recommend `live-review recommended` when current critic/citation evidence is mock, heuristic, local diagnostic, stale, or missing for the current manuscript hash.
- Recommend `quality-gate recommended` when live or acceptable evidence exists but no fresh quality-eval/qa-loop plan exists.
- Recommend `authoring-round recommended` only after an approved plan exists and review/gate evidence identifies machine-actionable manuscript improvements.
- Recommend `human-needed answer required` for `human_needed` plans; list exactly the decisions required.
- Recommend `materials missing` when factual paper drafting would require inventing claims, citations, figures, or results.

Do not run expensive live review or edit manuscripts from this skill unless the user separately asks for that workflow.
