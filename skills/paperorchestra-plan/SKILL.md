---
name: paperorchestra-plan
description: Create or revise a PaperOrchestra paper plan for author approval before drafting. Use after intake/material audit when the user needs thesis framing, section structure, RQs, evidence tables, figure plan, related-work search plan, or an approval-gated paper-plan.md; wraps OMX $plan/$ralplan-style planning and must not write the manuscript yet.
---

# PaperOrchestra Plan

Use this after `$paperorchestra-intake` or when materials and author intent are sufficient but the manuscript structure is not approved. The output is `paper-plan.md`, not `paper.full.tex`.

## Principle

Planning is a human-visible gate. Do not start authoring rounds until the plan is accepted or the user explicitly asks to bypass the gate.

Wrap OMX planning behavior: use `$plan`/`$ralplan` style tradeoff review for section structure, claims, evaluation shape, and risk boundaries. If OMX runtime is unavailable, perform the same planning directly and preserve the approval gate.

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

## Workflow

1. Read the current intake/material packet and inspect source artifacts read-only.
2. Identify the paper archetype: system pipeline, empirical evaluation, benchmark/resource, position, survey, tool/demo, etc.
3. Draft the thesis and contribution list with explicit claim boundaries.
4. Propose a concise section structure. Avoid placeholder section names like “Problem”, “Approach”, or “Findings” unless the target venue commonly uses them.
5. Map every section to why it exists and what evidence it uses.
6. Propose tables/figures with TODO cells where final numbers are not available.
7. Propose related-work search clusters and known seed papers, but do not fabricate citations.
8. Write `paper-plan.md` in the output workspace.
9. Stop for author approval or revision. Recommend `$paperorchestra-authoring-round` only after approval.

## paper-plan.md shape

```markdown
# PaperOrchestra Paper Plan

## One-sentence thesis

## Paper type and target format

## Contribution boundaries
### Allowed claims
### Disallowed claims
### Required caveats

## Research questions or evaluation questions

## Proposed section structure
For each section:
- title:
- rhetorical job:
- reader belief before:
- reader belief after:
- why this section exists:
- key content:
- evidence/materials:
- open TODOs:

## Tables and figures
- table/figure:
- purpose:
- source evidence:
- TODO fields:

## Related-work plan
- cluster:
- why needed:
- seed papers/queries:
- how it connects to our thesis:

## Author approval gate
- recommended next action:
- questions for the author:
```

## Stop condition

Stop when `paper-plan.md` exists and the next action is clear:

- author approves -> add `<!-- paperorchestra:plan-approved -->` to `paper-plan.md`, then `$paperorchestra-authoring-round`;
- author requests changes -> revise `$paperorchestra-plan`;
- material is insufficient -> return to `$paperorchestra-intake` or `$paperorchestra-status`.
