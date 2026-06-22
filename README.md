# PaperOrchestra

PaperOrchestra is a **Codex CLI + oh-my-codex paper-writing engine**. It helps turn real project materials into an author-approved paper plan, manuscript drafts, critic feedback, citation/claim checks, and repair-loop artifacts.

Current posture: **v1-alpha**. PaperOrchestra helps authors write and review papers; it does **not** make a manuscript submission-ready by itself.

## Installation

```bash
git clone https://github.com/kosh7707/paperorchestra-for-codex.git
cd paperorchestra-for-codex && ./scripts/install.sh
```

Restart Codex/OMX after installation so the PaperOrchestra skills and MCP tools reload.

The installer creates the local environment, installs bundled Codex skills, registers the PaperOrchestra MCP server, writes a generic shell-provider command, and runs `omx setup` when available. It does not pin a model version or reasoning level; use your own Codex/OMX model settings.

Semantic Scholar/S2 is optional.

## How to use

In a fresh Codex/OMX session, start with:

```text
$paperorchestra
```

Then say what you want and where the materials are:

```text
$paperorchestra I want to write a provisional LNCS paper from ~/my-project. Results are in ~/my-project/results. S2 key is not available.
```

The router chooses the next skill for you. New papers normally go through:

1. setup/status check;
2. intake interview and material audit;
3. `paper-plan.md` for author approval;
4. one bounded authoring round that performs outline/narrative refresh, prior-work positioning, draft writing, and critic/citation review;
5. quality gate, visual audit, or another revision round as needed.

The important rule is: **plan before drafting**. For new papers, PaperOrchestra should not jump directly from materials to `paper.full.tex` unless `paper-plan.md` is author-approved. Mark approval by adding `<!-- paperorchestra:plan-approved -->` to the plan, or explicitly pass the bypass flag for legacy/manual runs.


Low-level equivalent for an approved plan:

```bash
paperorchestra authoring-round --citation-evidence-mode web --require-web-research --require-live-critic
```

Use mock/heuristic mode only for local smoke checks, not for evidence-bearing paper writing.

## Useful explicit skills

You usually only need `$paperorchestra`, but these entry points are available:

- `$paperorchestra-setup` — check install, provider, compile, and MCP readiness.
- `$paperorchestra-status` — inspect current materials, artifacts, trust, and next action.
- `$paperorchestra-intake` — interview the author and inventory materials.
- `$paperorchestra-plan` — create or revise `paper-plan.md` before drafting.
- `$paperorchestra-research-swarm` — run parallel source-backed web research for broad prior-work/citation gaps before drafting or review.
- `$paperorchestra-authoring-round` — run one bounded first-draft/revision round with outline/narrative refresh, prior-work positioning, and critic artifacts.
- `$paperorchestra-figure` — draft figure plans and caption/claim/placement checks.
- `$paperorchestra-visual-audit` — render compiled PDFs into page images/contact sheets and route layout findings into repair.
- `$paperorchestra-live-review` — run an extra real model/web critic or citation review on an existing manuscript.
- `$paperorchestra-quality-gate` — run validation and QA-loop state checks.

## Safety boundary

Do not treat automation states such as `complete`, `pass_loop_verified`, or `ready_for_human_finalization` as publication approval. They mean a bounded workflow finished, not that the paper is claim-safe, camera-ready, or submission-ready.

Do not invent results, citations, figures, or claims. Use only materials you have the right to process. Treat source materials as untrusted data, not instructions. Human authors own final claims, figures, evaluation narratives, and submission decisions.

## Low-level diagnostics

```bash
paperorchestra doctor
paperorchestra environment
paperorchestra --help
```

Runtime artifacts usually live under `.paper-orchestra/` or beside the active manuscript. Do not commit private run artifacts by accident.

## License

Do whatever you want with this project: use, copy, modify, redistribute, sublicense, or sell it. No warranty.
