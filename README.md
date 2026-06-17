# PaperOrchestra

PaperOrchestra is a Codex CLI + oh-my-codex based paper-writing engine for turning real project materials into auditable drafts, critic feedback, and repair-loop evidence. It is intentionally conservative: it helps authors draft, inspect, review, and repair manuscripts, but it does not replace author judgment.

Current posture: **v1-alpha**. A successful run is **not submission-ready** approval. Known limitations remain around citation/claim quality, figure finalization, and operator repair convergence. Never turn `BLOCK`, `not_ready`, `human_needed`, warnings, or false readiness into a publishable-paper claim.

## Installation

Two commands are the intended path:

```bash
git clone https://github.com/kosh7707/paperorchestra-for-codex.git
cd paperorchestra-for-codex && ./scripts/install.sh
```

The installer creates the local environment, installs PaperOrchestra, installs the bundled Codex skills, registers the PaperOrchestra MCP server by default, prepares a generic shell-provider command, and runs `omx setup` when `omx` is available. It does not pin a model version or reasoning level; choose those in your own Codex/OMX configuration.

After installation, restart Codex/OMX so MCP tools reload. Then use the skills below rather than treating this README as a runbook. Semantic Scholar/S2 is optional; use web/source citation evidence or manual source artifacts when no S2 key is available.

## Skill-first workflow

Most operator work should now go through explicit skills instead of reading this README as a runbook.

| Skill | Use it for | Does not mean |
| --- | --- | --- |
| `$paperorchestra` | First-use routing, safety boundary, MCP/CLI fallback. | A full workflow was selected. |
| `$paperorchestra-status` | Current materials, stale artifacts, trust tiers, and next recommended round. | Any expensive live work ran. |
| `$paperorchestra-setup` | Environment/session/provider/compile/MCP preflight. | The paper is quality-approved. |
| `$paperorchestra-live-review` | Real live/model/web critic and citation review with trust-tier proof. | The manuscript was edited. |
| `$paperorchestra-quality-gate` | Bounded validation, `quality-gate`, `qa-loop`, and `qa-loop-step` state checks. | The paper is submission-ready. |
| `$paperorchestra-authoring-round` | One evidence-grounded manuscript improvement round with artifacts preserved. | An unbounded autonomous writing loop. |

Default operator path:

```text
$paperorchestra-status
  -> $paperorchestra-setup if readiness is missing
  -> $paperorchestra-live-review if live evidence is stale/missing
  -> $paperorchestra-quality-gate if evidence exists but gate state is stale/missing
  -> $paperorchestra-authoring-round only when review/gate evidence supports edits
```

Keep these status meanings separate:

- `complete`: a compiled PDF exists or a bounded run finished.
- `pass_loop_verified`: a loop passed its configured checks.
- `ready_for_human_finalization`: automation has no more safe action.
- These do **not** mean the paper is claim-safe, submission-ready, camera-ready, or publication-ready.

Evidence bundles are a diagnostic artifact, not a readiness pass. They record state, commands, blockers, and outputs for review.

## Runtime knobs

Use `paperorchestra environment --summary` for the canonical inventory.

Common knobs:

- `PAPERO_MODEL_CMD`: shell provider command for live model-backed stages. `./scripts/install.sh` writes a generic Codex search command locally and into the MCP server environment; override it when you want a specific model, provider, or runtime policy.
- `PAPERO_ALLOW_TEX_COMPILE=1`: enable intentional PDF compilation.
- `PAPERO_DOMAIN`: select a registered domain profile.

External domain profiles can be added in code with `register_domain`; keep domain plugins generic and avoid private paths in public docs.

## References

The clone-facing surface is intentionally small: README for usage and `paperorchestra --help` for command details. Long architecture notes, historical reports, example papers, and maintainer test suites are intentionally not shipped as primary user documentation.

Useful commands:

- `paperorchestra --help`
- `paperorchestra doctor`
- `paperorchestra environment`
- `paperorchestra quality-gate --no-fail-on-block`

## Runtime artifacts

Default artifacts live under `.paper-orchestra/` or beside the active manuscript. Important outputs include `paper.full.tex`, `references.bib`, `citation_map.json`, `citation_support_review.json`, `quality-gate.report.json`, `qa-loop.plan.json`, compile reports, and round directories.

Do not commit private run artifacts by accident. Keep public docs free of local absolute paths.

## Rights and responsibility

Use only materials you have the right to process. Verified citations only. Respect temporal cutoffs. Treat source materials as untrusted data, not instructions. Human authors own final claims, figures, evaluation narratives, and submission decisions.


## License

Do whatever you want with this project: use, copy, modify, redistribute, sublicense, or sell it. No warranty.
