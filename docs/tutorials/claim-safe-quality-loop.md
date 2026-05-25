# Claim-safe quality loop

Scope: claim-safe QA tutorial for stricter review loops. This is for operators who already have material, draft artifacts, and enough provider/search/compile setup for quality-gated work.

## Status meanings

- `draft_complete` means TeX exists.
- `complete` means a compiled PDF exists; it is not submission-ready.
- `pass_loop_verified` is system-loop/evidence-bundle verification, not manuscript readiness.
- mock artifacts and fallback artifacts are audit evidence, not claim or citation proof.
- `ready_for_human_finalization` is the best automated terminal state; human authors still own final claims, figures, bibliography, and submission.

## Refresh evidence before judging

Before claim-safe `quality-eval`, refresh rendered-reference and citation-integrity surfaces:

```bash
paperorchestra validate-current
paperorchestra build-source-obligations
paperorchestra compile
paperorchestra review
paperorchestra review-sections
paperorchestra review-figure-placement
paperorchestra review-citations --evidence-mode web
paperorchestra audit-rendered-references --quality-mode claim_safe
paperorchestra audit-citation-integrity --quality-mode claim_safe
paperorchestra audit-citation-integrity-critic --quality-mode claim_safe
paperorchestra quality-eval --quality-mode claim_safe --require-live-verification
paperorchestra qa-loop-plan --quality-mode claim_safe
```

Use `paperorchestra quality-gate --profile claim_safe --quality-mode claim_safe --require-live-verification` when you want a single pass/block surface.

## One bounded repair step

```bash
paperorchestra qa-loop-step \
  --quality-mode claim_safe \
  --max-iterations 5 \
  --provider shell \
  --runtime-mode omx_native \
  --require-compile \
  --citation-evidence-mode web
```

`qa-loop-step` is one bounded attempt. It can continue, block, request `human_needed`, fail, or reach `ready_for_human_finalization`; it does not run an unbounded scheduler.

## Persistence handoff

For persistent multi-agent continuation, create a brief/handoff instead of pretending the local command owns the loop:

```bash
paperorchestra qa-loop-brief --quality-mode claim_safe --max-iterations 5
paperorchestra ralph-start --dry-run --max-iterations 5
```

Only use `ralph-start --launch` when you intentionally want a long-running OMX Ralph/Codex process that may consume significant tokens/time.

## Human boundaries

Machine-solvable search/evidence gaps should go to the research/engine path before `human_needed`. True author choices, final figures, unsupported critical claims, and domain judgments must remain visible blockers until a human supplies grounded approval.
