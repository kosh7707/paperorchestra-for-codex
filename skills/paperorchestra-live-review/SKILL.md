---
name: paperorchestra-live-review
description: Run or verify a real PaperOrchestra live/model/web critic lane. Use when the user asks for live critic, real review, web citation review, trust-tier proof, or explicitly says not to take mock/heuristic/local diagnostic paths.
---

# PaperOrchestra Live Critic Review

Use this when the goal is to review the current manuscript with real provider evidence, not to edit the paper or run the whole QA state machine.

## Preflight first

Fail closed unless the critique command is actually run with a shell provider and web citation evidence:

```bash
paperorchestra critique --provider shell --provider-command "$PAPERO_MODEL_CMD" --citation-evidence-mode web
```

If preflight reports `mock_smoke`, `local_diagnostic`, or `heuristic_citation`, never claim live validation. Say what is missing and route to `$paperorchestra-setup`.

## Academic writing doctrine

Use `../paperorchestra/references/academic-writing.md` as the critic rubric when reviewing narrative quality. In addition to technical correctness, review paper-likeness:

- Is the paper archetype clear?
- Is `Phenomenon → Gap → Contribution → Evidence → Boundary → Implication` visible?
- Does each major section have a rhetorical job?
- Does each paragraph and sentence intent move the reader?
- Does Related Work position the manuscript rather than summarize papers?
- Are strong claims tied to evidence, citations, or caveats?

## OMX companion routing

Live review should stop after reporting evidence, but it must name the right follow-up workflow:

- `$autoresearch`: citation support is missing, weak, stale, or machine-solvable source discovery is needed.
- `$best-practice-research`: the critic flags venue conventions, section structure, terminology, or related-work positioning as nonstandard.
- `$ralph`: review findings are machine-actionable and the user wants a persistent repair loop over PaperOrchestra artifacts.
- `$ultraqa`: live review is already fresh and the user wants hostile final-readiness checks rather than another normal review.

## Run live review

Use an explicit output directory for review artifacts. Installed CLI fallback may not expose `--live`; in that surface, live review means `--provider shell` plus `--citation-evidence-mode web`. If `paperorchestra critique --help` shows `--live`, include it to fail closed on trust preflight:

```bash
paperorchestra critique \
  --provider shell \
  --provider-command "$PAPERO_MODEL_CMD" \
  --citation-evidence-mode web \
  --source-paper <paper.tex> \
  --output-dir <critic-run-dir>
```

## Report trust tiers

Always summarize:

- provider provenance
- review score or verdict
- citation support summary
- top revision suggestions
- artifacts written
- trust tier: `mock_smoke`, `local_diagnostic`, `heuristic_citation`, `live_model_review`, `web_citation_review`, or `claim_safe_live`

Stop after review. Do not auto-edit; route edits to `$paperorchestra-authoring-round`.
