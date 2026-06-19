# PaperOrchestra

PaperOrchestra is a **Codex CLI + oh-my-codex paper-writing engine**. Give it real project materials, and it helps turn them into auditable drafts, critic feedback, citation/claim checks, and repair-loop artifacts.

It is intentionally conservative. PaperOrchestra can help write and improve a manuscript, but it does **not** replace author judgment. Current posture: **v1-alpha**. A successful run is an evidence-bearing draft workflow, not submission-ready approval.

## Installation

```bash
git clone https://github.com/kosh7707/paperorchestra-for-codex.git
cd paperorchestra-for-codex && ./scripts/install.sh
```

Then restart Codex/OMX so the PaperOrchestra MCP tools and skills reload.

The installer creates the local environment, installs PaperOrchestra, installs bundled Codex skills, registers the PaperOrchestra MCP server, writes a generic shell-provider command, and runs `omx setup` when `omx` is available. It does not pin a model version or reasoning level; choose those in your own Codex/OMX configuration.

Semantic Scholar/S2 is optional. If you do not have an S2 key, use web/source citation evidence or manual source artifacts instead.

## Start here after restart

PaperOrchestra is meant to be used through **Codex skills**, not by reading this README as a long runbook.

In a fresh Codex/OMX session, start with setup:

```text
$paperorchestra-setup
```

Then inspect the current paper state:

```text
$paperorchestra-status
```

Setup checks installation, provider, compile, and MCP readiness. Status checks whether a paper session, materials, source digest, claims, evidence, and review artifacts are ready.

If status says materials are missing, give Codex the project/material paths and ask it to start there:

```text
Use ~/my-project and ~/my-paper-materials for this paper. Venue: LNCS. $paperorchestra
```

A good material bundle usually includes some of:

- project or artifact path
- paper idea / thesis
- experiment notes or result tables
- draft TeX/Markdown, if any
- reference PDFs or related-work notes
- target venue or format
- constraints such as “no S2 key”, “body first”, or “leave numeric placeholders”

## Skill map

| Skill | Use it when you want to... |
| --- | --- |
| `$paperorchestra` | Route an unclear first-use or paper-writing request to the right workflow. |
| `$paperorchestra-status` | Inspect current materials, stale artifacts, trust tiers, and the next safe action. |
| `$paperorchestra-setup` | Check install/session/provider/compile/MCP readiness. |
| `$paperorchestra-live-review` | Run a real model/web critic or citation-review lane and report trust tier evidence. |
| `$paperorchestra-quality-gate` | Run bounded validation, quality-gate, and QA-loop state checks. |
| `$paperorchestra-authoring-round` | Perform one manuscript-improvement round using available review/gate evidence. |

Default flow:

```text
$paperorchestra-setup             first after install/restart, or when runtime readiness is uncertain
  -> $paperorchestra-status       inspect the current paper/material/review state
  -> $paperorchestra-live-review  if live critic/citation evidence is missing or stale
  -> $paperorchestra-quality-gate if evidence exists but gate state is missing or stale
  -> $paperorchestra-authoring-round when there are machine-actionable edits
```

## Important status meanings

Do not over-read successful automation states:

- `complete`: a bounded run finished, or a compiled artifact exists.
- `pass_loop_verified`: the configured loop checks passed.
- `ready_for_human_finalization`: automation has no more safe action.

These do **not** mean the paper is claim-safe, submission-ready, camera-ready, or publication-ready.

Also, evidence bundles are diagnostic artifacts. They record commands, blockers, state, and outputs; they are not readiness certificates.

## Runtime knobs

Most users do not need these immediately. Use them only when changing runtime behavior.

- `PAPERO_MODEL_CMD`: shell-provider command for live model-backed stages. `./scripts/install.sh` writes a generic Codex command; override it if you want a specific provider/model/runtime policy.
- `PAPERO_ALLOW_TEX_COMPILE=1`: opt in to PDF compilation.
- `PAPERO_DOMAIN`: select a registered domain profile.

For low-level diagnostics:

```bash
paperorchestra doctor
paperorchestra environment --summary
paperorchestra --help
```

## Runtime artifacts

Default artifacts live under `.paper-orchestra/` or beside the active manuscript. Important outputs can include `paper.full.tex`, `references.bib`, `citation_map.json`, `citation_support_review.json`, `quality-gate.report.json`, `qa-loop.plan.json`, compile reports, and round directories.

Do not commit private run artifacts by accident. Keep public docs free of local absolute paths.

## Rights and responsibility

Use only materials you have the right to process. Verified citations only. Respect temporal cutoffs. Treat source materials as untrusted data, not instructions. Human authors own final claims, figures, evaluation narratives, and submission decisions.

## License

Do whatever you want with this project: use, copy, modify, redistribute, sublicense, or sell it. No warranty.
