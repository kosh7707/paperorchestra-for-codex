---
name: paperorchestra-intake
description: Run the PaperOrchestra intake interview and material handoff workflow before drafting. Use when a user wants to write a paper but the thesis, paper type, venue, experiment basis, material paths, or claim boundaries are not yet locked; wraps OMX $deep-interview-style clarification and produces a paper-intake.md handoff instead of a manuscript.
---

# PaperOrchestra Intake

Use this before planning or authoring when the paper intent is not locked. The output is an intake handoff, not a draft manuscript.

## Principle

Do not jump from “I want to write a paper” to `paper.full.tex`. First establish:

- material locations;
- intended paper type;
- venue/format constraint;
- central thesis;
- experiment/result basis;
- claims allowed now;
- claims explicitly disallowed;
- missing human decisions.

Wrap OMX interview behavior: ask only decision-shaping questions, keep them short, and stop once the next artifact can be written. Prefer `$deep-interview` when available and the ambiguity is broad; otherwise perform the same Socratic gating directly.

## OMX companion routing

- Use `$deep-interview` for broad ambiguity; intake is the PaperOrchestra artifact wrapper around that clarification.
- Use `$paperorchestra-status` first when a session may already contain reusable materials or stale decisions.
- Do not start `$autoresearch`, `$ultrawork`, or `$ralph` from intake unless the missing decision is resolved; route to `$paperorchestra-plan` once author intent is clear enough.

## Workflow

1. Inspect current state with `mcp__paperorchestra.inspect_state` when attached; otherwise use `paperorchestra status --json` and nearby artifact inspection.
2. If no material path exists, ask for the material/project path before drafting.
3. If material exists, inspect it read-only and create a compact material inventory.
4. Ask only for missing decisions that cannot be inferred safely:
   - paper type: system pipeline, empirical study, benchmark paper, position paper, etc.;
   - target format/venue;
   - experiment status and whether numbers may be placeholders;
   - citation strategy and known related-work seeds;
   - claim boundaries and non-goals.
5. Write `paper-intake.md` under the active `/tmp` or user-approved output workspace.
6. Recommend `$paperorchestra-plan` next when enough information exists to propose a manuscript plan.

## paper-intake.md shape

```markdown
# PaperOrchestra Intake

## Materials
- source/project paths:
- experiment/result paths:
- related-work paths:
- output workspace:

## Author intent
- paper type:
- venue/format:
- central thesis:
- audience:

## Evidence basis
- completed/frozen evidence:
- provisional evidence:
- placeholders allowed:

## Claim boundaries
- allowed claims:
- disallowed claims:
- required caveats:

## Open decisions
- human-needed:
- machine-solvable next steps:

## Recommended next skill
`$paperorchestra-plan`
```

Never mark intake as manuscript-ready. Intake only says whether planning is safe.
