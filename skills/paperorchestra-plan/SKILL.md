---
name: paperorchestra-plan
description: Create or revise a PaperOrchestra paper-plan.md v3 contract for author approval before drafting. Use after intake/material audit when thesis framing, section structure, claim/evidence boundaries, figures, related-work positioning, or approval gates are not locked; wraps OMX $plan/$ralplan-style planning and must not write the manuscript yet.
---

# PaperOrchestra Plan

## Invocation contract

Before executing any `$skill`, `omx`, `codex`, MCP, or PaperOrchestra CLI action from this skill, read `../paperorchestra/references/invocation-contract.md` and follow it. Required companion skills must be invoked, not merely recommended.

Use this after `$deep-interview` and `$paperorchestra-intake`, or when the current user message already contains all required intake decisions and materials. The output is `paper-plan.md`, not `paper.full.tex`.

## Principle

Planning is a human-visible gate. Do not start authoring rounds until the plan is accepted or the user explicitly asks to bypass the gate.

`paper-plan.md` is the **single author-approved contract**. It should stay compact enough for a human to approve. Paragraph-level execution detail belongs in a derived `paper-skeleton.md` after approval; the skeleton is never a second approval source.

Wrap OMX planning behavior: use `$plan`/`$ralplan` style tradeoff review for section structure, claims, evaluation shape, and risk boundaries. If OMX runtime is unavailable, perform the same planning directly and preserve the approval gate.

## Pre-plan intake gate

Do not write `paper-plan.md` for a new paper until `$deep-interview` has resolved the author intent and a real intake has happened. A generated material inventory, repository README, or inferred thesis is not enough.

Before planning, verify that `paper-intake.md` exists from a resolved `$deep-interview` handoff, or that the current user message explicitly answers all intake decisions: paper type, target venue/format, central thesis, experiment/result maturity, placeholder policy, citation strategy, allowed claims, disallowed claims, and non-goals. A valid resolved interview should have a referenced `.omx/specs/deep-interview-*.md` artifact or equivalent explicit current-turn answers. If any author-blocking decision is missing, route back to `$deep-interview` / `$paperorchestra-intake` instead of drafting the plan.

If an existing `paper-intake.md` lists unresolved `human-needed` decisions that affect thesis, claim strength, evidence boundaries, venue, or placeholder policy, route back to `$deep-interview` and then `$paperorchestra-intake`; do not “fill in” those decisions from source materials.

## Academic writing doctrine

Read `../paperorchestra/references/academic-writing.md` before proposing or revising the section plan. The plan must instantiate:

```text
Phenomenon → Gap → Contribution → Evidence → Boundary → Implication
```

For every proposed section, write its rhetorical job and the reader belief transition:

```text
section title:
rhetorical job:
reader belief before:
reader belief after:
evidence used:
failure mode if omitted:
```

## OMX companion routing

- Prefer `$ralplan` when thesis, section order, RQs, evaluation design, or claim boundaries have multiple plausible choices.
- Use `$best-practice-research` when the plan depends on venue norms, common section names, comparable-paper narrative structure, or reviewer expectations.
- Use `$autoresearch` only for bounded related-work seed discovery needed to make the plan credible; do not turn planning into full citation writing.
- Use `$ultrawork` only when independent planning lanes are clearly separable, such as material inventory, related-work seed clustering, and table/figure planning.
- Recommend `$ultragoal` after the author approves a substantial implementation/repair plan that should be completed as durable sequential stories.
- Recommend `$team` with `$ultragoal` when approved follow-up work has separable lanes, such as plan-gate code, skeleton generation, review integration, and verification.
- Reserve `$ralph` for explicit single-owner persistence requests; do not present it as the default durable follow-up when `$ultragoal` fits.

## Workflow

1. Read the current intake/material packet and inspect source artifacts read-only. Confirm the intake gate above is satisfied before writing or revising `paper-plan.md`.
2. Identify the paper archetype: system pipeline, empirical evaluation, benchmark/resource, position, survey, tool/demo, etc.
3. Draft the thesis, argument contract, contribution list, non-contributions, and required caveats.
4. Register only thesis-critical claims in a claim-support ledger. Use stable IDs (`C1`, `E1`, `S1`, `F1`, `T1`, `RW1`, `Q1`) so later critic, citation, visual, and repair artifacts can reference the contract without restating it.
5. Propose a concise section blueprint. Avoid placeholder section names like “Problem”, “Approach”, or “Findings” unless the target venue commonly uses them.
6. Map every section to rhetorical job, reader belief transition, claim refs, evidence refs, key moves, section-specific exclusions, completion checks, and blockers.
7. Propose tables/figures with TODO cells where final numbers are not available. For each planned figure, include figure rhetorical job, supported claim, source evidence, caption contract, placement contract (`figure` vs `figure*` when known), output form, and TODO/final-artwork status. Route complex pipeline, architecture, taxonomy, teaser, result-summary, case-study, threat-model, or visual-abstract figures to `$paperorchestra-figure`.
8. Propose related-work positioning clusters and known seed papers/queries, but do not fabricate citations.
9. Write `paper-plan.md` in the output workspace. For new plans, prefer a v3 approval contract and leave it unapproved until the author accepts it. When the author approves, use MCP `approve_plan` when attached or verified `paperorchestra approve-plan` when the CLI exposes it so the approval becomes a hash-bound hidden approval record. Use a CLI approval command only if the installed `paperorchestra --help` surface actually exposes one; otherwise record the explicit author approval text or marker in the output workspace and do not invent an unavailable CLI command.
10. Stop for author approval or revision. Recommend `$paperorchestra-authoring-round` only after approval; recommend `$ultragoal` only for durable implementation/repair follow-up, not ordinary manuscript prose drafting.

## paper-plan.md v3 shape

```markdown
# PaperOrchestra Paper Plan

## 1. Approval summary
- working title:
- target venue/format:
- audience:
- primary archetype:
- evidence maturity:
- one-sentence thesis:
- author-blocking decisions:

## 2. Argument contract
| Move | Paper-specific contract |
| --- | --- |
| Phenomenon | |
| Gap | |
| Contribution | |
| Evidence standard | |
| Boundary | |
| Implication | |

### Contributions
### Non-contributions
### Required caveats
### Re-approval triggers

## 3. Claim-support ledger
| ID | Claim and maximum strength | Claim class | Support mode | Evidence/status | Boundary or wording guard | Destination |
| --- | --- | --- | --- | --- | --- | --- |

## 4. Evidence registry
| ID | Locator | What it proves | What it does not prove | Status |
| --- | --- | --- | --- | --- |

## 5. Questions and archetype obligations
| ID | Kind | Purpose | Design | Claim refs | Validity condition |
| --- | --- | --- | --- | --- | --- |

## 6. Section blueprint
For each section:
- title:
- rhetorical job:
- reader belief before:
- reader belief after:
- claim refs:
- evidence refs:
- key move sequence:
- section-specific exclusions:
- completion check:
- approximate budget:
- open blocker:

## 7. Tables and figures
| ID | Type | Claim refs | Evidence refs | Reader move | Caption must establish | Placement constraint/TODO |
| --- | --- | --- | --- | --- | --- | --- |

## 8. Related-work positioning
| Cluster | Argument role | What we concede | Contrast axis | Gap/claim refs | Seeds or queries | Status |
| --- | --- | --- | --- | --- | --- | --- |

## 9. Placeholder and blocker policy
- numerical placeholders allowed:
- qualitative trend language allowed:
- citations may remain TODO:
- figures may remain conceptual:
- must not infer or fabricate:
- author-blocking decisions:
- machine-solvable tasks:
- conditions that block authoring:
- conditions that block finalization:

## 10. Approval contract
- approval covers:
- approval does not certify:
- approved revision:
- approved by:
- approval command: MCP `approve_plan` when attached; otherwise use an installed CLI approval command only if `paperorchestra --help` exposes one, or record explicit author approval text/marker.
```

Do not put full material inventories, detailed citation TODOs, or paragraph-level intent in `paper-plan.md`; route those to sidecar evidence artifacts or the derived `paper-skeleton.md`.

## Stop condition

Stop when `paper-plan.md` exists and the next action is clear:

- author approves -> record approval with MCP `approve_plan` when attached, with an exposed CLI approval command if available, or with explicit author approval text/marker; then `$paperorchestra-authoring-round`;
- author requests changes -> revise `$paperorchestra-plan`;
- material is insufficient -> return to `$paperorchestra-intake` or `$paperorchestra-status`.
