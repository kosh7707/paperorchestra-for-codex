---
name: paperorchestra-quality-gate
description: Run the bounded PaperOrchestra quality gate and QA-loop state transition. Use for quality gate, claim-safe checks, qa-loop/qa-loop-step, human_needed handling, or deciding whether the current paper is blocked, failed, or ready for human finalization.
---

# PaperOrchestra Quality Gate

Use this for state-machine verification. It may call critics, but its job is to decide the current quality/repair state, not to perform an unbounded writing loop.

## Bounded order

Run only the needed suffix if fresh artifacts already exist; otherwise follow this order. The citation-support stage is `critique --citation-evidence-mode web`:

```bash
paperorchestra quality-gate --no-fail-on-block
paperorchestra critique --provider shell --provider-command "$PAPERO_MODEL_CMD" --citation-evidence-mode web
paperorchestra qa-loop --quality-mode claim_safe --require-live-verification
paperorchestra qa-loop-step --quality-mode claim_safe --max-iterations 1
```

`run` alone is draft generation, not full quality approval. A full quality gate must include validation, compile where allowed, critic/citation evidence, `quality-gate`, `qa-loop`, and at most a bounded `qa-loop-step`.

## Academic writing doctrine

Use `../paperorchestra/references/academic-writing.md` for manuscript-quality checks beyond syntax and compile status. The gate should report:

- narrative coherence against `Phenomenon → Gap → Contribution → Evidence → Boundary → Implication`;
- section rhetorical alignment;
- sentence-intent alignment;
- claim-evidence-boundary alignment;
- Related Work positioning quality;
- whether paper-likeness failures are machine-actionable or require the author.

## OMX companion routing

Quality gate decides the next state; it does not silently perform an unbounded repair loop. Route follow-up work explicitly:

- `$ralph`: machine-actionable repair steps exist and the user wants the loop to continue until the bounded PaperOrchestra stop condition.
- `$ultrawork`: independent repair families can run in parallel, such as citations, section structure, reproducibility text, and figure/table cleanup.
- `$autoresearch`: gate failures are citation/source-evidence gaps that can be solved by research.
- `$best-practice-research`: failures concern venue norms, conventional phrasing, section shape, or reviewer expectations.
- `$ultraqa`: fresh live review and quality artifacts exist and the next need is adversarial final QA.

## Stop states

Treat these as correct terminal reports:

- `human_needed`: stop and list exact author decisions required.
- `failed`: stop and report failing codes/artifacts.
- `ready_for_human_finalization`: stop; this is **not submission-ready**.
- `continue`: run at most the requested bounded step count.

Do not hide warnings, do not loop forever, and do not mark human-only finalization as automated success.
