---
name: paperorchestra-figure
description: Design, draft, review, or generate evidence-bearing paper figures for PaperOrchestra manuscripts. Use when a paper plan, section, review, or quality gate needs pipeline, architecture, taxonomy, teaser, result-summary, case-study, or visual-abstract figures; handles caption/claim alignment, one-column vs two-column LaTeX placement, and routes to imagegen only for bitmap illustrations.
---

# PaperOrchestra Figure

## Invocation contract

Before executing any `$skill`, `omx`, `codex`, MCP, or PaperOrchestra CLI action from this skill, read `../paperorchestra/references/invocation-contract.md` and follow it. Required companion skills must be invoked, not merely recommended.

Use this skill for paper figures, not generic image requests. A figure is a scholarly argument object: it must support a claim, fit the manuscript layout, and have a caption that explains why the reader should care.

## Figure intent contract

Before generating or editing a figure, write this compact contract:

```text
Figure type: pipeline | architecture | taxonomy | teaser | result-summary | case-study | threat-model | visual-abstract
rhetorical job:
supported claim:
source evidence:
reader belief before:
reader belief after:
caption contract:
placement contract:
output form: Mermaid | SVG | TikZ | LaTeX snippet | image prompt | bitmap illustration | caption only
```

Reject decorative figures. If the figure has no supported claim or source evidence, route back to `$paperorchestra-plan` or ask for the missing evidence.

## Placement contract

Decide layout before visual detail:

- Before recommending `figure*`, inspect the target template/guidelines and confirm the manuscript is actually in two-column mode.
- **one-column**: use LaTeX `figure` for narrow diagrams, small taxonomy blocks, single result panels, or figures intended to sit near the paragraph that interprets them. Target column width.
- **two-column**: use LaTeX `figure*` for architecture diagrams, wide pipelines, multi-panel summaries, or figures whose labels would become unreadable at column width. Note: figure* is for two-column templates only; it may float differently by class/package, often near the top of a page. Target page width and place near the top of a page when the template requires it.
- Do not emit a final LaTeX snippet that uses `figure*` unless two-column mode is confirmed by the template/guidelines or manuscript class.
- If this is an unknown template or the venue/template is unknown, use `figure` or mark the environment TODO; do not finalize `figure*`.
- Captions must remain informative when the figure floats away from the paragraph.
- After changing placement, require compile or quality-gate verification and inspect/update `figure-placement-review.json` when that artifact exists or is being produced.
- After compile, route rendered-page readability, overflow, and cross-figure style checks to `$paperorchestra-visual-audit`; this skill owns figure intent/caption/placement, not full-PDF page screenshot acceptance.

Always report:

```text
Recommended LaTeX environment: figure | figure*
Width target: column width | page width
Float risk:
Caption dependency:
```

## Caption evidence map

For every caption, create or update this evidence map:

```text
caption sentence:
supported claim:
source artifact/data/code/citation:
caveat/boundary:
```

If any caption claim exceeds the evidence, downgrade or reject the caption/figure before generation. Do not let a beautiful figure create a stronger claim than the manuscript can support.

## PaperOrchestra figure artifacts

Inspect and preserve these artifacts when present:

- `plot_manifest.json`: intended plots/figures and their source data or generation recipe.
- `plot_assets.json`: generated figure files, formats, and paths.
- `plot_captions.json`: caption drafts and caption evidence maps.
- `figure-placement-review.json`: one-column/two-column, `figure`/`figure*`, width, and float-risk checks.
- `page-layout-review.json`: rendered PDF page-image audit for overflow, readability, and cross-figure style consistency.
- `visual_repair_brief.json`: page-visual repair handoff generated before user escalation.
- `figure_gate.report.json`: final figure quality-gate findings.

Artifact availability checklist:

```text
plot_manifest.json: present / missing / stale / not applicable
plot_assets.json: present / missing / stale / not applicable
plot_captions.json: present / missing / stale / not applicable
figure-placement-review.json: present / missing / stale / not applicable
figure_gate.report.json: present / missing / stale / not applicable
```

For a figure-bearing manuscript, expected figure artifacts must not silently disappear. If an expected artifact is missing or stale, block and route to `$paperorchestra-figure` or the owning quality/status workflow before claiming the figure is integrated.

## Output policy

Use vector-first outputs for precise paper content:

- Prefer **Mermaid**, **SVG**, or **TikZ** for pipeline, architecture, taxonomy, and method diagrams.
- Prefer table/plot code or a plot spec for result-summary figures when data drives the claim.
- Use `imagegen` only when the requested output is a bitmap illustration, visual abstract, teaser image, or presentation-style conceptual art where exact geometry is not the evidence.
- Do not use imagegen for diagrams that must preserve exact node labels, arrows, numeric results, code paths, or reproducible layout.
- If bitmap output is claimed, the agent must actually call the imagegen skill/tool and report the generated artifact. If no imagegen call was made, label the result `prompt only / no image generated` and do not imply that an image file exists.

Before generating anything, consider cheaper alternatives:

- remove the figure if it does not support a necessary claim;
- convert to prose if a sentence explains the point more clearly;
- convert to table when the evidence is categorical or numeric;
- defer to human final artwork when the concept is right but the final visual style should be designed manually.

## OMX companion routing

- `$best-practice-research`: use when venue norms, figure placement conventions, caption style, or comparable-paper visual patterns need external evidence.
- `$ultrawork`: use when several independent figure variants can be explored in parallel, such as pipeline vs architecture vs taxonomy alternatives.
- `$visual-verdict`: use when a rendered bitmap or screenshot-like figure needs visual QA against a reference.
- `$paperorchestra-visual-audit`: use when the compiled PDF pages, tables, or multiple figures must be inspected together as rendered output.
- `$ralph`: use when the user wants a persistent figure repair loop over generated artifacts, captions, placement, and manuscript integration.

## Workflow

1. Start with current PaperOrchestra session/status inspection unless purely reviewing a provided snippet. The figure skill must route back to the owning workflow (`$paperorchestra-plan`, `$paperorchestra-authoring-round`, `$paperorchestra-quality-gate`, or `$paperorchestra-live-review`) and must not become a parallel paper workflow.
2. Inspect the paper plan, section draft, or review finding.
3. Fill the Figure intent contract.
4. Choose one-column vs two-column placement and `figure` vs `figure*`.
5. Build the Caption evidence map and reject/downgrade unsupported caption claims; weak caption rejected/downgraded is the correct outcome when the caption is not self-contained, not evidence-mapped, or stronger than the evidence.
6. Choose output form:
   - Mermaid/SVG/TikZ for precise diagrams;
   - LaTeX snippet when placement/caption is the main need;
   - imagegen only for bitmap illustration.
7. Draft the caption:
   - first sentence: what the figure shows;
   - second sentence: what claim it supports;
   - optional final sentence: key caveat or reading order.
8. Return an artifact card and route follow-up edits to the owning paper workflow.

## Review checklist

Check every figure for:

- claim alignment: does it support a stated paper claim?
- evidence alignment: are components grounded in code, experiments, sources, or plan artifacts?
- caption sufficiency: can the reader understand the figure if it floats?
- placement: does `figure` vs `figure*` match one-column/two-column readability?
- visual necessity: would prose or a table be clearer?
- no invented components, citations, metrics, labels, or arrows.

## Final card

```text
Figure type:
Rhetorical job:
Supported claim:
Source evidence:
Output form:
Recommended LaTeX environment:
Width target:
Caption draft:
Caption evidence map:
Self-contained/floating-caption check:
Weak-caption status:
Generation/edit artifact:
Risks/TODOs:
Next paper skill:
```
