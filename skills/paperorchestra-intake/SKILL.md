---
name: paperorchestra-intake
description: Run the PaperOrchestra intake interview and material handoff workflow before drafting. Use when a user wants to write a paper but the thesis, paper type, venue, experiment basis, material paths, or claim boundaries are not yet locked; wraps OMX $deep-interview-style clarification and produces a paper-intake.md handoff instead of a manuscript.
---

# PaperOrchestra Intake

## Invocation contract

Before executing any `$skill`, `omx`, `codex`, MCP, or PaperOrchestra CLI action from this skill, read `../paperorchestra/references/invocation-contract.md` and follow it. Required companion skills must be invoked, not merely recommended.

Use this after `$deep-interview` has clarified the author intent, or when the current user message already contains all required intent decisions. The output is an intake handoff, not a draft manuscript.

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

Wrap OMX interview behavior: invoke `$deep-interview` before writing intake whenever author intent is missing or ambiguous. Ask only decision-shaping questions, keep them short, and stop once the next artifact can be written. Use direct Socratic gating only as an explicit fallback outside an available OMX runtime; state that fallback before asking, mark the PaperOrchestra intake blocked, and do not write `paper-intake.md` in the same turn.

## Mandatory deep-interview gate

For a fresh paper-writing request, invoke `$deep-interview` and perform at least one author interview turn before writing `paper-intake.md`, unless the user already supplied explicit answers to all required decisions in the current request. Repository documents may suggest a thesis or venue, but they do not count as author approval.

If the user supplies only a material path, a read-only constraint, or an output directory, inspect materials read-only and create at most a material inventory/status note in the output workspace. Then hand that inventory to `$deep-interview` and stop with its short questions. Do **not** write `paper-intake.md`, `paper-plan.md`, `paper-skeleton.md`, or manuscript files yet.

Required decisions before writing `paper-intake.md`:

- paper type / primary archetype;
- target venue/format or explicit “unspecified is OK”;
- central thesis or preferred framing;
- experiment/result maturity and whether placeholders are allowed;
- citation strategy or known related-work seeds;
- allowed claims, disallowed claims, and non-goals.

Required invocation evidence before writing `paper-intake.md`:

- either the current user message explicitly answers every required decision above;
- or a resolved `$deep-interview` handoff artifact path under `.omx/specs/deep-interview-*.md`, created from the same material inventory/output workspace.

If neither exists, stop after inventory and execute `$deep-interview`; do not create an intake handoff.

## Academic writing doctrine

Use `../paperorchestra/references/academic-writing.md` to classify the paper archetype and fill the generic paper arc before planning:

```text
Phenomenon → Gap → Contribution → Evidence → Boundary → Implication
```

Do not assume every paper is a systems paper. Intake should distinguish systems, methodology/benchmark, empirical, survey/review, and position-paper intents.

## Fresh-start boundary

If the user explicitly requests a fresh start, context reset, or new paper session, do not reuse prior project paths, claims, venue choices, experiment assumptions, or old intake artifacts. Inspect current PaperOrchestra state, then ask for the material path again if the current reset-scope user message has not supplied it.

## OMX companion routing

- Use `$deep-interview` first for fresh or broad ambiguity; intake is the PaperOrchestra artifact wrapper around that clarification, not a replacement for it.
- Use `$paperorchestra-status` first when a session may already contain reusable materials or stale decisions.
- Do not start `$autoresearch`, `$ultrawork`, or `$ralph` from intake unless the missing decision is resolved; route to `$paperorchestra-plan` once author intent is clear enough.

## Workflow

1. Inspect current state with `mcp__paperorchestra.inspect_state` when attached; otherwise use `paperorchestra status --json` and nearby artifact inspection.
2. If no material path exists, ask for the material/project path before drafting.
3. If material exists, inspect it read-only and create a compact material inventory. This inventory is not an intake handoff and must not imply author intent is locked.
4. If any required decision is missing, invoke `$deep-interview` with the inventory and ask only for missing decisions that cannot be inferred safely:
   - paper type: system pipeline, empirical study, benchmark paper, position paper, etc.;
   - target format/venue;
   - experiment status and whether numbers may be placeholders;
   - citation strategy and known related-work seeds;
   - claim boundaries and non-goals.
5. Write `paper-intake.md` only after `$deep-interview` produces a handoff artifact or the current user message supplies the required decisions, or after the author explicitly authorizes placeholders for the still-open decisions. Use a user-supplied output workspace or a newly created, clearly named workspace for this run; do not reuse an old `/tmp` directory unless the user explicitly identifies it as current.
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
- primary archetype:
- venue/format:
- central thesis:
- audience:
- phenomenon:
- gap:
- contribution type:
- intended implication:

## Evidence basis
- completed/frozen evidence:
- provisional evidence:
- placeholders allowed:

## Claim boundaries
- allowed claims:
- disallowed claims:
- required caveats:
- boundary of generalization:

## Open decisions
- human-needed:
- machine-solvable next steps:

## Recommended next skill
`$paperorchestra-plan`
```

Never mark intake as manuscript-ready. Intake only says whether planning is safe.
