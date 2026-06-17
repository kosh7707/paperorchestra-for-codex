---
name: paperorchestra-quality-gate
description: Run the bounded PaperOrchestra validation, quality-eval, and QA-loop state transition. Use for quality gate, claim-safe checks, qa-loop-plan/qa-loop-step, human_needed handling, or deciding whether the current paper is blocked, failed, or ready for human finalization.
---

# PaperOrchestra Quality Gate

Use this for state-machine verification. It may call critics, but its job is to decide the current quality/repair state, not to perform an unbounded writing loop.

## Bounded order

Run only the needed suffix if fresh artifacts already exist; otherwise follow this order. The citation-support stage is `review-citations --evidence-mode web`:

```bash
paperorchestra validate-current
paperorchestra build-source-obligations
paperorchestra compile
paperorchestra review --provider shell --provider-command "$PAPERO_MODEL_CMD"
paperorchestra review-sections
paperorchestra review-citations --provider shell --provider-command "$PAPERO_MODEL_CMD" --evidence-mode web
paperorchestra quality-eval --quality-mode draft
paperorchestra quality-eval --quality-mode claim_safe --require-live-verification
paperorchestra qa-loop-plan --quality-mode claim_safe
paperorchestra qa-loop-step --quality-mode claim_safe --max-iterations 1
```

`run` alone is draft generation, not full quality approval. A full quality gate must include validation, compile where allowed, critic/citation evidence, `quality-eval --quality-mode`, `qa-loop-plan`, and at most a bounded `qa-loop-step`.

## Stop states

Treat these as correct terminal reports:

- `human_needed`: stop and list exact author decisions required.
- `failed`: stop and report failing codes/artifacts.
- `ready_for_human_finalization`: stop; this is **not submission-ready**.
- `continue`: run at most the requested bounded step count.

Do not hide warnings, do not loop forever, and do not mark human-only finalization as automated success.
