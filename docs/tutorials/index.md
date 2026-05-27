# PaperOrchestra tutorials

Scope: first-use tutorial index for operators who need a path through the docs without reading the full README. These tutorials are practical runbooks; `README.md` stays the product map and `ENVIRONMENT.md` stays the environment/setup sheet.

PaperOrchestra is v1-alpha. A successful run creates auditable artifacts, not submission-ready approval. Treat `complete`, mock/demo output, and `pass_loop_verified` as evidence states, not final paper acceptance. Human authors still own final claims, figures, bibliography, and submission decisions.

## Pick one path

| Need | Tutorial | What it proves |
| --- | --- | --- |
| Start safely from a fresh checkout | [`start.md`](start.md) | Local install and command routing work without live calls. |
| Produce one offline artifact set | [`mock-demo.md`](mock-demo.md) | The mock/demo pipeline can create a draft and exportable artifacts; this is not citation-fidelity proof. |
| Validate Docker/container QA | [`docker-container-qa.md`](docker-container-qa.md) | Container entry, fresh install, mock demo, export bundle, and PDF compile path are usable. |
| Act as human QA for rendered PDFs | [`rendered-pdf-human-qa.md`](rendered-pdf-human-qa.md) | A reviewer inspected rendered pages, including title/top matter and layout, and left hash-bound evidence. |
| Run stricter claim-safe loops | [`claim-safe-quality-loop.md`](claim-safe-quality-loop.md) | The quality loop can continue, block, or reach human finalization without false readiness. |
| Review citation density or weak support | [`claim-safe-quality-loop.md`](claim-safe-quality-loop.md) plus [`rendered-pdf-human-qa.md`](rendered-pdf-human-qa.md) | Citation count, weak support, and paper-owned claim scope are kept visible for human judgment instead of hidden as success. |

## Document roles

- `README.md` — project overview, status semantics, and route map.
- `ENVIRONMENT.md` — environment variables, prerequisites, and readiness profiles.
- `skills/paperorchestra/SKILL.md` — Codex/MCP operation contract.
- `docs/quality-gate-state-machine.md` — normative lifecycle and gate semantics.

If the implementation falls short of a tutorial expectation, record the evidence under `.omx/` or the run artifact directory and keep the limitation visible instead of rewriting the tutorial to overclaim.
