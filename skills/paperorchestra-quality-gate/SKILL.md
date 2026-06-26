---
name: paperorchestra-quality-gate
description: Run the bounded PaperOrchestra quality gate and QA-loop state transition. Use for quality gate, claim-safe checks, qa-loop/qa-loop-step, human_needed handling, or deciding whether the current paper is blocked, failed, or ready for human finalization.
---

# PaperOrchestra Quality Gate

## Invocation contract

Before executing any `$skill`, `omx`, `codex`, MCP, or PaperOrchestra CLI action from this skill, read `../paperorchestra/references/invocation-contract.md` and follow it. Required companion skills must be invoked, not merely recommended.

Use this for state-machine verification. It may call critics, but its job is to decide the current quality/repair state, not to perform an unbounded writing loop.

## Bounded order

Run only the needed suffix if fresh artifacts already exist; otherwise follow this order. Preferred MCP/source gate: `quality_gate(...)` or a CLI gate only when `paperorchestra quality-gate --help` verifies it exists on the exact surface you will run. Current source/venv CLI fallback is `critique` → `quality-gate` → `qa-loop` → bounded `qa-loop-step`. The citation-support stage is `critique --citation-evidence-mode web`:

```bash
paperorchestra critique --provider shell --provider-command "$PAPERO_MODEL_CMD" --citation-evidence-mode web
paperorchestra quality-gate --quality-mode claim_safe --require-live-verification
paperorchestra qa-loop --quality-mode claim_safe --require-live-verification
paperorchestra qa-loop-step --quality-mode claim_safe --max-iterations 1
```

Legacy installations may expose older staged commands such as `validate-current`, `quality-eval`, or `qa-loop-plan`. Use them only after that same CLI surface verifies them with `--help`; otherwise treat current `quality-gate`/`qa-loop` as the documented path.

`run` alone is draft generation, not full quality approval. A full quality gate must include validation/quality-gate state, compile where allowed, critic/citation evidence, a repair plan (`qa-loop` or legacy `qa-loop-plan`), and at most a bounded `qa-loop-step`.

After every state-changing gate command, run `paperorchestra status --json` and inspect the expected `quality-eval.json`, `qa-loop.plan.json`, `qa-loop-history.jsonl`, validation JSON, and repair-step artifacts before reporting the gate state.

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

For a compiled manuscript, treat page-visual artifacts as `present / missing / stale / pending reviewer / failing / not applicable`. Missing/stale `page-layout-review.json` or failed render evidence should route to `$paperorchestra-visual-audit` or a verified visual-audit command; do not assume the installed CLI exposes `paperorchestra visual-audit`. Machine-actionable visual findings should create `visual_repair_brief.json` and then `visual_repair_candidate.json`, routing repair back to PaperOrchestra/Critic before asking the user. Human escalation is reserved for final artwork, semantic visual evidence disputes, aesthetic preference, or adoption/rejection of an already prepared candidate.

## OMX companion routing

Quality gate decides the next state; it does not silently perform an unbounded repair loop. Route follow-up work explicitly:

- `$ralph`: machine-actionable repair steps exist and the user wants the loop to continue until the bounded PaperOrchestra stop condition.
- `$ultrawork`: independent repair families can run in parallel, such as citations, section structure, reproducibility text, and figure/table cleanup.
- `$paperorchestra-research-swarm`: gate failures are broad/multi-cluster citation/source-evidence gaps that can be solved by parallel web/source research before another repair or review pass.
- `$autoresearch`: gate failures are single-lane citation/source-evidence gaps that can be solved by validator-gated research, or the validator gate inside `$paperorchestra-research-swarm`.
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
