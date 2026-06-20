---
name: paperorchestra-quality-gate
description: Run the bounded PaperOrchestra quality gate and QA-loop state transition. Use for quality gate, claim-safe checks, qa-loop/qa-loop-step, human_needed handling, or deciding whether the current paper is blocked, failed, or ready for human finalization.
---

# PaperOrchestra Quality Gate

Use this for state-machine verification. It may call critics, but its job is to decide the current quality/repair state, not to perform an unbounded writing loop.

## Bounded order

Run only the needed suffix if fresh artifacts already exist; otherwise follow this order. Preferred MCP/source gate: `quality_gate(...)` or, when verified available, `paperorchestra quality-gate --no-fail-on-block`. Installed CLI fallback: `validate-current` → `critique` → `quality-eval` → `qa-loop-plan` → bounded `qa-loop-step`. The citation-support stage is `critique --citation-evidence-mode web`:

```bash
paperorchestra validate-current
paperorchestra critique --provider shell --provider-command "$PAPERO_MODEL_CMD" --citation-evidence-mode web
paperorchestra quality-eval --quality-mode claim_safe --require-live-verification
paperorchestra qa-loop-plan --quality-mode claim_safe --require-live-verification
paperorchestra qa-loop-step --quality-mode claim_safe --max-iterations 1
```

`run` alone is draft generation, not full quality approval. A full quality gate must include validation, compile where allowed, critic/citation evidence, `quality-eval`, `qa-loop-plan`, and at most a bounded `qa-loop-step`.

## Academic writing doctrine

Use `../paperorchestra/references/academic-writing.md` for manuscript-quality checks beyond syntax and compile status. The gate should report:

- narrative coherence against `Phenomenon → Gap → Contribution → Evidence → Boundary → Implication`;
- section rhetorical alignment;
- sentence-intent alignment;
- claim-evidence-boundary alignment;
- figure-caption alignment and figure placement;
- rendered-page visual/layout evidence: page contact sheets, table overflow, figure readability, one-column/two-column fit, cross-figure style consistency;
- figure artifacts: `plot_manifest.json`, `plot_assets.json`, `plot_captions.json`, `figure-placement-review.json`, `page-layout-review.json`, `visual_repair_brief.json`, `visual_repair_candidate.json`, `figure_gate.report.json`;
- Related Work positioning quality;
- whether paper-likeness failures are machine-actionable or require the author.

For a figure-bearing manuscript, treat figure artifact availability as `present / missing / stale / not applicable`. Missing or stale expected figure artifacts are quality-gate blockers: route to `$paperorchestra-figure` instead of marking the figure/caption/placement accepted.

For a compiled manuscript, treat page-visual artifacts as `present / missing / stale / pending reviewer / failing / not applicable`. Missing/stale `page-layout-review.json` or failed render evidence should be an automatic `paperorchestra visual-audit` step. Machine-actionable visual findings should create `visual_repair_brief.json` and then `visual_repair_candidate.json`, routing repair back to PaperOrchestra/Critic before asking the user. Human escalation is reserved for final artwork, semantic visual evidence disputes, aesthetic preference, or adoption/rejection of an already prepared candidate.

## OMX companion routing

Quality gate decides the next state; it does not silently perform an unbounded repair loop. Route follow-up work explicitly:

- `$ralph`: machine-actionable repair steps exist and the user wants the loop to continue until the bounded PaperOrchestra stop condition.
- `$ultrawork`: independent repair families can run in parallel, such as citations, section structure, reproducibility text, and figure/table cleanup.
- `$autoresearch`: gate failures are citation/source-evidence gaps that can be solved by research.
- `$best-practice-research`: failures concern venue norms, conventional phrasing, section shape, or reviewer expectations.
- `$ultraqa`: fresh live review and quality artifacts exist and the next need is adversarial final QA.
- `$paperorchestra-figure`: failures concern figure-caption alignment, figure placement, unsupported visuals, or one-column/two-column readability.
- `$paperorchestra-visual-audit`: failures concern rendered PDF page layout, table overflow, figure readability, contact-sheet review, or cross-figure visual consistency.

## Stop states

Treat these as correct terminal reports:

- `human_needed`: stop and list exact author decisions required.
- `failed`: stop and report failing codes/artifacts.
- `ready_for_human_finalization`: stop; this is **not submission-ready**.
- `continue`: run at most the requested bounded step count.

Do not hide warnings, do not loop forever, and do not mark human-only finalization as automated success.
