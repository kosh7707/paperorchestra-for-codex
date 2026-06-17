---
name: paperorchestra-live-review
description: Run or verify a real PaperOrchestra live/model/web critic lane. Use when the user asks for live critic, real review, web citation review, trust-tier proof, or explicitly says not to take mock/heuristic/local diagnostic paths.
---

# PaperOrchestra Live Review

Use this when the goal is to review the current manuscript with real provider evidence, not to edit the paper or run the whole QA state machine.

## Preflight first

Fail closed unless preflight permits live claims. The conceptual gate is `critic-preflight --live`:

```bash
paperorchestra critic-preflight --provider shell --provider-command "$PAPERO_MODEL_CMD" --citation-evidence-mode web --live
```

If preflight reports `mock_smoke`, `local_diagnostic`, or `heuristic_citation`, never claim live validation. Say what is missing and route to `$paperorchestra-setup`.

## Run live review

Use an explicit output directory for review artifacts. The required live command shape is `critique --live`, and citation support uses `review-citations --evidence-mode web`:

```bash
paperorchestra critique \
  --live \
  --provider shell \
  --provider-command "$PAPERO_MODEL_CMD" \
  --citation-evidence-mode web \
  --source-paper <paper.tex> \
  --output-dir <critic-run-dir>

paperorchestra review-citations \
  --provider shell \
  --provider-command "$PAPERO_MODEL_CMD" \
  --evidence-mode web \
  --output <critic-run-dir>/citation_support_review.json
```

`review-citations --evidence-mode web` emits stderr heartbeat progress and a progress JSONL checkpoint for resumability.

## Report trust tiers

Always summarize:

- provider provenance
- review score or verdict
- citation support summary
- top revision suggestions
- artifacts written
- trust tier: `mock_smoke`, `local_diagnostic`, `heuristic_citation`, `live_model_review`, `web_citation_review`, or `claim_safe_live`

Stop after review. Do not auto-edit; route edits to `$paperorchestra-authoring-round`.
