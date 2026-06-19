---
name: paperorchestra-authoring-round
description: Run one bounded PaperOrchestra manuscript-improvement round. Use when the user asks to improve, revise, or strengthen a paper draft using current materials, live review, and quality-gate evidence while preserving artifacts in a named round directory.
---

# PaperOrchestra Authoring Round

Use this for one manuscript round, not for indefinite autonomous writing. For new papers, require an approved `paper-plan.md` or an explicit user instruction to bypass the planning gate.

## Round recipe

1. Start with `$paperorchestra-status` and create a round directory such as `.paper-orchestra/round-N/`.
2. Check for `paper-plan.md` with an author-approval marker such as `<!-- paperorchestra:plan-approved -->`, or equivalent approved plan artifact. If missing, stop and route to `$paperorchestra-plan` unless the user explicitly bypassed planning.
3. If live evidence is missing or stale, run `$paperorchestra-live-review` first.
4. Run `$paperorchestra-quality-gate` to get the current bounded gate state.
5. If the state is `human_needed`, do not edit on human_needed; present the required author decisions.
6. Apply a bounded manuscript edit only if the user asked for edits and the gate/review evidence identifies machine-actionable changes.
7. Re-run compile/validate and any affected review artifacts.
8. Write an artifact manifest listing inputs, outputs, hashes, review/gate files, and remaining blockers.

## Edit boundaries

- Do not invent results, citations, figures, or metrics.
- Do not convert unapproved plans into manuscript prose unless the user explicitly says to proceed.
- Preserve current manuscript unless explicitly editing.
- Prefer section-scoped edits over whole-paper rewrites.
- Keep all artifacts in the round directory.
- Report compile/validate status after the edit.

## Final card

```text
Round directory:
Inputs used:
Live review:
Quality gate:
Edits applied:
Compile/validate:
Artifacts:
Remaining risks:
Next recommended skill:
```
