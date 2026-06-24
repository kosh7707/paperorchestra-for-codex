---
name: paperorchestra-figure
description: Design, draft, review, generate, and repair evidence-bearing PaperOrchestra manuscript figures through a mandatory plan → Critic validation → imagegen bitmap generation → AI-artifact/visual QA → repair loop. Use when a paper plan, section, review, or quality gate needs pipeline, architecture, taxonomy, teaser, result-summary, case-study, threat-model, or visual-abstract figures; handles caption/claim alignment, one-column vs two-column LaTeX placement, Ralph-backed iteration, visual-verdict/page-audit checks, and forbids TikZ/SVG/Mermaid as final generated figure content.
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
output form: imagegen bitmap asset | image prompt + generated image | LaTeX placement snippet for generated bitmap | caption only for review-only tasks
```

Reject decorative figures. If the figure has no supported claim or source evidence, route back to `$paperorchestra-plan` or ask for the missing evidence.

## Mandatory figure Ralph loop

Every new or replacement evidence-bearing figure must run this loop before it can be claimed integrated. Treat this as required even when the user asks for a quick figure. Skip only for explicitly review-only/caption-only tasks, and record the skip reason.

```text
figure plan -> Critic validation + reinforcement -> imagegen bitmap generation -> figure visual QA -> repair/regenerate -> compile/render -> page visual audit -> accept or continue
```

Use `$ralph` as the persistence wrapper when the current session has OMX runtime support or the user asks to keep going through the figure. Ralph's stop condition is not "an image exists"; it is: plan accepted, generated bitmap persisted, AI-artifact/visual findings resolved or explicitly human-owned, compiled PDF rendered, and figure/page artifacts recorded. If runtime Ralph is unavailable, execute the same loop locally and record `ralph_unavailable` in the figure manifest.

Required artifacts for every generated/replacement figure:

- `figure-plan.<id>.md`: figure intent contract, claim/caption/placement contract, prompt strategy, and acceptance checks.
- `figure-critic.<id>.json`: Critic verdict before generation. Must include `verdict`, `blocking_issues[]`, `reinforcements[]`, and `acceptance_checks[]`.
- `plot_manifest.json`, `plot_assets.json`, `plot_captions.json`: updated for the selected bitmap.
- `figure-visual-findings.<id>.json`: visual-verdict/vision/Critic findings for the bitmap or rendered page. It must explicitly address AI-generated-artifact tells and publication-figure readability.
- `figure-placement-review.json`: refreshed after LaTeX placement changes.
- `page-layout-review.json`: refreshed after compile/render; cannot be TeX-only.
- `figure_gate.report.json`: refreshed after artifact checks; it must block matched/generated/realized figure slots whose plan, Critic, or visual findings artifact is missing or failing.

Critic validation must happen before generation. The Critic should reject or reinforce the plan when the figure is a faux figure, overcrowded, decorative, too local-term-heavy, caption-dependent, unsupported by evidence, or better expressed as prose/table. Critic reinforcement should simplify the visual claim, reduce labels, move exact terms/numbers into the caption/table, and define the visual hierarchy before imagegen is invoked.

## AI-artifact and publication visual QA

For every generated or replacement bitmap, inspect the raw bitmap and the rendered PDF page. Fail or request repair for:

- garbled, blurry, misspelled, or too-small text; labels that would not survive IEEE page-width or column-width rendering;
- warped geometry, inconsistent arrows, impossible joins, object bleeding, strange shadows/lighting, overdecorated stock-art sheen, glossy stock-art sheen, or unnecessary photorealism;
- too many colors, random color semantics, red/green-only distinctions, low contrast, color behind text, or reliance on color alone;
- decorative icons, fake UI chrome, excessive detail, or a "faux figure" that is really a list/table dressed up as art;
- unsupported local implementation terms in the image when the caption/table could carry the exact detail more safely;
- unreadable crop, bad aspect ratio, table/figure overlap, float clump, excessive whitespace, or caption drift after rendering.

The default pass threshold is strict: no blocking visual finding, no unresolved `visual_review_pending`, no AI-artifact tell that would make the figure look machine-generated or unserious, and no caption/claim mismatch. If the reviewer finds only aesthetic preference that cannot be resolved objectively, mark it `human_needed` instead of pretending the figure passed.

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
figure-plan.<id>.md: present / missing / stale / not applicable
figure-critic.<id>.json: present / missing / stale / not applicable
figure-visual-findings.<id>.json: present / missing / stale / not applicable
```

For a figure-bearing manuscript, expected figure artifacts must not silently disappear. If an expected artifact is missing or stale, block and route to `$paperorchestra-figure` or the owning quality/status workflow before claiming the figure is integrated.

## Command surface

Use the installed `imagegen` skill/tool for figure asset generation. PaperOrchestra MCP/source/CLI tools remain useful for state inspection, artifact indexing, placement review, and quality gates, but they must not replace imagegen with TikZ/SVG/Mermaid generation.

If using installed CLI fallback surfaces, verify each command with `--help` before use. These commands are for orchestration or review, not a reason to bypass imagegen:

```bash
paperorchestra review-figure-placement --output figure-placement-review.json
```

For evidence-bearing figure work, generate or edit the bitmap through imagegen, then inspect or write `plot_manifest.json`, `plot_assets.json`, `plot_captions.json`, and `figure-placement-review.json` before claiming the figure artifacts are ready.

## Output policy

Use imagegen as the mandatory generation path for PaperOrchestra figures:

- Do **not** create Mermaid, SVG, TikZ, Graphviz, canvas, or other vector/code-native diagrams as final generated figure content.
- For every new or replacement paper figure asset, invoke the installed `imagegen` skill/tool as part of the mandatory figure Ralph loop, persist the selected bitmap into the PaperOrchestra workspace, and pass AI-artifact/publication visual QA before claiming the figure exists.
- Use LaTeX only for placement around the generated bitmap, for example `\includegraphics`, figure width, label, and caption. Do not use LaTeX/TikZ to draw the figure itself.
- For pipeline, architecture, taxonomy, method, case-study, threat-model, and visual-abstract figures, translate exact evidence requirements into an imagegen prompt with short, high-level labels. Put exact terminology, verdict mappings, numeric values, and caveats in the caption/evidence map rather than relying on tiny in-image text.
- For result-summary figures, use imagegen for the visual summary graphic. Keep exact numbers in tables or captions unless the user explicitly accepts approximate in-image text.
- If an imagegen call cannot be made, stop with a blocker or return `prompt only / no image generated`; do not substitute TikZ/SVG/Mermaid and do not imply that an image file exists.

Before generating anything, still consider whether a figure is necessary:

- remove the figure if it does not support a necessary claim;
- convert to prose if a sentence explains the point more clearly;
- convert to a table when exact categorical or numeric evidence matters more than visual rhetoric;
- defer to human final artwork only when the concept is right but no imagegen output should be treated as final.

## OMX companion routing

- `$best-practice-research`: use when venue norms, figure placement conventions, caption style, or comparable-paper visual patterns need external evidence.
- `$ultrawork`: use when several independent figure variants can be explored in parallel, such as pipeline vs architecture vs taxonomy alternatives.
- `$visual-verdict`: mandatory after bitmap generation or rendered-page screenshot capture; use it to inspect readability, visual hierarchy, and AI-artifact tells before the next edit.
- `$paperorchestra-visual-audit`: mandatory after compile for integrated figures; use `--require-ai-artifact-check --require-publication-figure-check` when available.
- `$ralph`: mandatory wrapper for every new or replacement evidence-bearing figure when OMX runtime is available; otherwise mirror the same loop locally and record the skip reason.

## Workflow

1. Start with current PaperOrchestra session/status inspection unless purely reviewing a provided snippet. The figure skill must route back to the owning workflow (`$paperorchestra-plan`, `$paperorchestra-authoring-round`, `$paperorchestra-quality-gate`, or `$paperorchestra-live-review`) and must not become a parallel paper workflow.
2. Inspect the paper plan, section draft, or review finding.
3. Fill the Figure intent contract and write `figure-plan.<id>.md`.
4. Choose one-column vs two-column placement and `figure` vs `figure*`.
5. Build the Caption evidence map and reject/downgrade unsupported caption claims; weak caption rejected/downgraded is the correct outcome when the caption is not self-contained, not evidence-mapped, or stronger than the evidence.
6. Run Critic validation before generation and write `figure-critic.<id>.json`; reinforce the plan until the Critic verdict is non-blocking.
7. Choose output form:
   - imagegen bitmap asset for every new or replacement figure;
   - LaTeX placement snippet only to embed the generated bitmap;
   - caption only when the task is explicitly review-only and no new figure asset is requested.
8. Invoke imagegen for generated assets, save the selected output into the PaperOrchestra workspace, and record the image path in `plot_assets.json` or the round artifact manifest before claiming success.
9. Run visual-verdict/vision review on the bitmap or rendered page and write `figure-visual-findings.<id>.json`; if it reports AI-artifact, readability, hierarchy, or publication-fit problems, repair/regenerate before continuing.
10. Draft the caption:
   - first sentence: what the figure shows;
   - second sentence: what claim it supports;
   - optional final sentence: key caveat or reading order.
11. Compile, run figure-placement review, run paperorchestra visual-audit on rendered pages, run/write `figure_gate.report.json`, and continue the Ralph loop until visual findings pass and the figure gate no longer blocks, or the issue becomes explicit `human_needed`.
12. Return an artifact card and route follow-up edits to the owning paper workflow.

## Review checklist

Check every figure for:

- claim alignment: does it support a stated paper claim?
- evidence alignment: are components grounded in code, experiments, sources, or plan artifacts?
- caption sufficiency: can the reader understand the figure if it floats?
- placement: does `figure` vs `figure*` match one-column/two-column readability?
- visual necessity: would prose or a table be clearer?
- no invented components, citations, metrics, labels, or arrows; if imagegen introduces unsupported detail, reject or regenerate the asset.
- no AI-generated-artifact tells: garbled text, warped geometry, object bleeding, inconsistent lighting/shadows, fake UI chrome, or stock-art gloss.
- publication-fit: readable at final IEEE column/page width, restrained palette, colorblind-safe semantics, enough whitespace, no faux-figure/list-with-icons smell.

## Final card

```text
Figure type:
Rhetorical job:
Supported claim:
Source evidence:
Output form:
Imagegen prompt:
Figure plan artifact:
Critic validation artifact:
Generated image artifact:
Visual findings artifact:
Ralph loop state / skip reason:
Recommended LaTeX environment:
Width target:
Caption draft:
Caption evidence map:
Self-contained/floating-caption check:
Weak-caption status:
Generation/edit artifact:
AI-artifact/publication QA verdict:
Risks/TODOs:
Next paper skill:
```
