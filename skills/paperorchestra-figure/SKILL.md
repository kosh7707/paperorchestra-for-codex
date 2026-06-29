---
name: paperorchestra-figure
description: Design, draft, review, generate, and repair evidence-bearing PaperOrchestra manuscript figures through mandatory imagegen participation, an output-form gate, Critic validation, source-of-truth rendering/generation, AI-artifact/publication QA, and repair loop. Use when a paper plan, section, review, or quality gate needs pipeline, architecture, taxonomy, teaser, result-summary, case-study, threat-model, visual-abstract, or imagegen-assisted figure concepts; handles caption/claim alignment, one-column vs two-column LaTeX placement, Ralph-backed iteration, visual-verdict/page-audit checks, imagegen concept/style artifacts, deterministic exact-label final assets, and venue-permitted non-exact imagegen bitmap finals.
---

# PaperOrchestra Figure

## Invocation contract

Before executing any `$skill`, `omx`, `codex`, MCP, or PaperOrchestra CLI action from this skill, read `../paperorchestra/references/invocation-contract.md` and follow it. Required companion skills must be invoked, not merely recommended.

Use this skill for paper figures, not generic image requests. A figure is a scholarly argument object: it must support a claim, fit the manuscript layout, and have a caption that explains why the reader should care.

## Publication-rhetoric gate

Before generation, decide whether the figure is a **paper figure** or an internal slide/diagram. Reject or redesign the plan when the figure depends on slide-like scaffolding rather than visual argument.

Hard rejection patterns:

- a title inside the figure that restates the caption or paper claim;
- a legend whose categories require rereading before the pipeline can be understood;
- prose panels such as "Evidence contract" that are paragraphs disguised as graphics;
- offline/evaluation/helper lanes mixed into a runtime architecture figure;
- box-and-arrow chains with no clear data/control semantics, decision point, or visual hierarchy;
- random arrow colors, palette semantics not explained by labels, or color-only meaning;
- pastel card grids, decorative badges, fake UI chrome, or "AI slide" styling;
- labels likely below 9 pt at final IEEE column/page width;
- a figure that would still be unclear if all colors were converted to grayscale.

For pipeline/architecture figures, require a one-sentence `figure_message`, then make every visual element serve that message. Prefer one main reading path, neutral process arrows, and at most one accented decision branch. Put benchmark labels, caveats, and long definitions in the caption or prose unless they are part of the runtime mechanism being depicted.

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
figure_message:
source-of-truth artifact:
source SHA-256:
venue AI policy:
output form: deterministic vector/PDF/PNG/SVG render | deterministic code/listing/table/plot asset | imagegen bitmap final | imagegen concept/style reference + deterministic final asset | LaTeX placement snippet | caption only for review-only tasks
imagegen participation: required concept/style reference | final bitmap art | skipped only for explicit review-only/caption-only task
imagegen role: concept_only | style_reference | final_art
imagegen prompt artifact:
imagegen result artifact or session evidence:
```

Reject decorative figures. If the figure has no supported claim or source evidence, route back to `$paperorchestra-plan` or ask for the missing evidence.

## Mandatory figure Ralph loop

Every new or replacement evidence-bearing figure must run this loop before it can be claimed integrated. Treat this as required even when the user asks for a quick figure. Skip only for explicitly review-only/caption-only tasks, and record the skip reason.

```text
figure plan -> output-form gate -> Architect design -> imagegen concept/final generation -> Critic validation + reinforcement -> render/generate selected source-of-truth artifact -> figure visual QA -> repair/regenerate -> compile/render -> page visual audit -> accept or continue
```

Use `$ralph` as the persistence wrapper when the current session has OMX runtime support or the user asks to keep going through the figure. Ralph's stop condition is not "an image exists"; it is: plan accepted, output-form gate recorded, imagegen participation recorded, source-of-truth artifact persisted with SHA-256, final embed path recorded, AI-artifact/visual findings resolved or explicitly human-owned, compiled PDF rendered, and figure/page artifacts recorded. If runtime Ralph is unavailable, execute the same loop locally and record `ralph_unavailable` in the figure manifest.

Required artifacts for every generated/replacement figure:

- `figure-plan.<id>.md`: figure intent contract, claim/caption/placement contract, prompt strategy, and acceptance checks.
- `figure-architect.<id>.json`: Architect design verdict before generation. Must include `candidate_designs[]`, selected design, rejected alternatives, composition/layout rules, typography/color rules, arrow/data-flow rules, and exact acceptance criteria. Do not let the main agent silently replace this with its own ad-hoc plan when a new/replacement figure is requested.
- `figure-critic.<id>.json`: Critic verdict before generation. Must include `verdict`, `blocking_issues[]`, `reinforcements[]`, and `acceptance_checks[]`.
- `imagegen-concepts.<id>.json` or equivalent manifest entry: imagegen prompt, output role (`concept_only`, `style_reference`, or `final_art`), result artifact path when the tool exposes one, or session evidence when it does not. This artifact is required for every new/replacement evidence-bearing figure unless the task is explicitly review-only/caption-only.
- `plot_manifest.json`, `plot_assets.json`, `plot_captions.json`: updated for imagegen participation, the selected/final asset, output form, source-of-truth artifact, source SHA-256, and caption evidence map.
- `figure-visual-findings.<id>.json`: visual-verdict/vision/Critic findings for the final asset or rendered page. It must explicitly address AI-generated-artifact tells and publication-figure readability.
- `figure-placement-review.json`: refreshed after LaTeX placement changes.
- `page-layout-review.json`: refreshed after compile/render; cannot be TeX-only.
- `figure_gate.report.json`: refreshed after artifact checks; it must block matched/generated/realized figure slots whose plan, Critic, or visual findings artifact is missing or failing.

Architect design must happen before image generation or deterministic rendering. When native subagents are available and the user requested figure generation/replacement, spawn or invoke an `architect` lane for the figure design unless the task is explicitly review-only/caption-only. The Architect must design the visual argument, not draw the final asset: propose 2--3 viable compositions, select one, explain why alternatives were rejected, set layout/typography/color/arrow rules, and define acceptance checks. Record this in `figure-architect.<id>.json`.

Imagegen participation must be a real invocation or a blocking record. For exact-label scientific figures, imagegen is concept/style evidence and the deterministic source remains final authority; however, do not satisfy the imagegen gate with prose saying "imagegen was invoked" unless there is a prompt artifact plus generated result path, tool-session evidence, or an explicit `imagegen_unavailable` / `prompt_only_no_image_generated` blocker.

Critic validation must happen after the Architect design and imagegen concept/style evidence, but before final integration. When native subagents are available and the user requested figure generation/replacement, spawn or invoke a `critic` lane unless the task is explicitly review-only/caption-only. The Critic should reject or reinforce the plan when the figure is a faux figure, overcrowded, decorative, too local-term-heavy, caption-dependent, unsupported by evidence, better expressed as prose/table, or fails the publication-rhetoric gate. Critic reinforcement should simplify the visual claim, reduce labels, preserve exact terms/numbers in deterministic source-of-truth assets or caption/table evidence maps, and define the visual hierarchy before final render/integration.

Critic validation must explicitly answer:

```text
paper_figure_not_slide: pass | fail
single_visual_message: pass | fail
legend_dependency: none | acceptable | blocking
runtime_vs_evaluation_mixed: no | acceptable | blocking
prose_disguised_as_graphic: no | blocking
arrow_semantics: clear | blocking
grayscale_readability: pass | fail
minimum_label_size: pass | fail
```

Any `blocking` or `fail` answer above blocks generation or integration until the figure is redesigned.

## AI-artifact and publication visual QA

For every generated or replacement final asset, inspect the raw asset and the rendered PDF page. This applies to deterministic outputs as well as imagegen outputs. Fail or request repair for:

- garbled, blurry, misspelled, or too-small text; labels that would not survive IEEE page-width or column-width rendering;
- warped geometry, inconsistent arrows, impossible joins, object bleeding, strange shadows/lighting, overdecorated stock-art sheen, glossy stock-art sheen, or unnecessary photorealism;
- too many colors, random color semantics, red/green-only distinctions, low contrast, color behind text, or reliance on color alone;
- decorative icons, fake UI chrome, excessive detail, or a "faux figure" that is really a list/table dressed up as art;
- unsupported local implementation terms in the image when the caption/table could carry the exact detail more safely;
- unreadable crop, bad aspect ratio, table/figure overlap, float clump, excessive whitespace, or caption drift after rendering.

Acceptance gates:

- `figure_message`: one sentence that states what the reader should learn.
- source-of-truth artifact and SHA-256 are mandatory for final evidence-bearing figures.
- readability: block text that would render below 8 pt equivalent; target 9--10 pt or larger at final embedded width.
- color: use 3--4 semantic colors maximum; no color-only semantics; pass grayscale/colorblind-safe review.
- venue AI final-art gate: unknown venue policy means deterministic-only for evidence-bearing exact figures; final imagegen bitmap art requires explicit venue/policy allowance and disclosure.
- rendered-page proof: page visual audit is required for deterministic outputs and imagegen outputs.

The default pass threshold is strict: no blocking visual finding, no unresolved `visual_review_pending`, no AI-artifact tell that would make the figure look machine-generated or unserious, and no caption/claim mismatch. If the reviewer finds only aesthetic preference that cannot be resolved objectively, mark it `human_needed` instead of pretending the figure passed.

Do not pass a figure only because text is legible, arrows do not cross, and labels are deterministic. Those are necessary but insufficient. A figure can be technically clean and still fail if it reads like a slide, mixes unrelated lanes, or requires the caption to explain its basic structure.

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

Use the output-form gate before choosing tools:

- Deterministic exact-label figures may use local script/vector/TikZ/SVG/Graphviz/Pillow/LaTeX-listing/table/plot sources when those are the source of truth. Export/embed as PDF, PNG, or SVG according to the venue/template and record the source path plus SHA-256.
- Use the installed `imagegen` skill/tool for every new/replacement evidence-bearing figure. For exact-label/data/code/arrow figures, the imagegen output is mandatory concept/style evidence, not final authority. For non-exact conceptual art, imagegen may be final art only when venue policy allows it. Imagegen is not a substitute for deterministic source-of-truth rendering when exact labels, arrows, code semantics, or numeric values carry the claim.
- PaperOrchestra MCP/source/CLI tools remain useful for state inspection, artifact indexing, placement review, visual/page audit, and quality gates. They do not remove the need for source-of-truth artifacts, caption evidence maps, or rendered-page proof.

If using CLI fallback surfaces, verify each command with `--help` on the exact surface you will run (PATH-installed console, checkout `.venv`, or source-module invocation). Do not call undocumented commands such as `paperorchestra review-figure-placement` unless that same surface lists them. When the verified surface exposes `visual-audit`, integrated rendered-page checks use:

```bash
.venv/bin/paperorchestra visual-audit --help  # or the verified paperorchestra surface
.venv/bin/paperorchestra visual-audit \
  --output page-layout-review.json \
  --require-ai-artifact-check \
  --require-publication-figure-check
```

For figure-only placement metadata, write or update `figure-placement-review.json` from inspected manuscript/template facts, or use a verified source/helper command if the selected surface exposes one; do not invent a console command or reuse a command observed only on a different PaperOrchestra installation.

For evidence-bearing figure work, render/generate the selected final asset, then inspect or write `plot_manifest.json`, `plot_assets.json`, `plot_captions.json`, and `figure-placement-review.json` before claiming the figure artifacts are ready.

## Output policy

Use mandatory imagegen participation, not mandatory imagegen final authority. The output-form gate must decide whether imagegen is final art or concept/style evidence before deterministic rendering:

| Figure requirement | Default output form | Imagegen role | Required proof |
| --- | --- | --- | --- |
| exact-label pipeline, architecture, method, taxonomy, threat-model, or trust-boundary diagram | deterministic vector/PDF/PNG/SVG source-of-truth render | required concept/style reference | imagegen prompt/result metadata plus source path + SHA-256, caption evidence map, rendered-page audit |
| result-summary plot, numeric chart, queue summary, or metric panel | deterministic script/data plot asset | required concept/style reference | imagegen prompt/result metadata plus data/script hash, plotted values check, rendered-page audit |
| case-study, failure anatomy, code idiom, or listing | LaTeX listing or deterministic diagram/listing asset | required concept/style reference | imagegen prompt/result metadata plus code/source citation, source hash, rendered-page audit |
| teaser, visual abstract, or non-exact conceptual illustration | imagegen bitmap final only when venue policy allows | final art or concept reference | prompt, generated asset path, disclosure/policy evidence, AI-artifact/publication QA |
| mixed exact+illustrative figure | deterministic final asset with imagegen concept/style reference | concept/style reference, not final authority | concept metadata plus deterministic source path/SHA and page audit |
| review-only caption/placement task | caption or LaTeX placement snippet only | none unless explicitly requested | caption evidence map or placement review |

Hard defaults:

- Every new/replacement evidence-bearing figure must invoke imagegen once or record a blocking `imagegen_unavailable` / `prompt_only_no_image_generated` status. Do not claim a figure loop is complete without imagegen participation evidence.
- Exact-label, data-bearing, arrow-bearing, code-semantic, or rule-semantic figures default to deterministic source-of-truth final assets.
- Unknown venue AI policy means no final imagegen bitmap for evidence-bearing exact figures; use deterministic final art or mark human final artwork required.
- Imagegen is mandatory for concept/style exploration and remains valid for non-exact visual art, but it must not be the final authority for exact text, arrows, data, or code semantics.
- Deterministic assets are allowed as final generated figure content when their source, evidence, caption map, SHA-256, and rendered-page audit are recorded. Do not reintroduce a blanket ban on TikZ/SVG/Mermaid/Graphviz/vector/code-native sources.
- Mermaid, TikZ, SVG, Graphviz, canvas, HTML, Pillow/PIL, or LaTeX listings are acceptable only when they are deterministic, source-backed, reviewable, and exported/embedded in a venue-compatible form. Do not use them to invent unsupported diagrams.
- If an imagegen call cannot be made for an imagegen-final task, stop with a blocker or return `prompt only / no image generated`; do not imply that an image file exists.
- If an imagegen call cannot be made for an exact-label deterministic-final task, record `prompt_only_no_image_generated` and keep the figure in a blocked or conditional state; do not mark the mandatory imagegen gate satisfied.
- For imagegen-concept + deterministic final asset paths, record the imagegen prompt/result role as `concept_only` or `style_reference`, then render the exact-label final asset locally and record the render source plus final asset path/hash in `plot_assets.json`.
- Use LaTeX placement snippets to embed final assets, for example `\includegraphics`, figure width, label, and caption. Do not use placement snippets as evidence that the figure itself was reviewed.

Before generating anything, still consider whether a figure is necessary:

- remove the figure if it does not support a necessary claim;
- convert to prose if a sentence explains the point more clearly;
- convert to a table when exact categorical or numeric evidence matters more than visual rhetoric;
- defer to human final artwork only when the concept is right but no generated/deterministic output should be treated as final.

## OMX companion routing

- `$best-practice-research`: use when venue norms, figure placement conventions, caption style, or comparable-paper visual patterns need external evidence.
- `$ultrawork`: use when several independent figure variants can be explored in parallel, such as pipeline vs architecture vs taxonomy alternatives.
- `$visual-verdict`: mandatory after final asset render/generation or rendered-page screenshot capture; use it to inspect readability, visual hierarchy, and AI-artifact tells before the next edit.
- `$paperorchestra-visual-audit`: mandatory after compile for integrated figures; use `--require-ai-artifact-check --require-publication-figure-check` when available.
- `$ralph`: mandatory wrapper for every new or replacement evidence-bearing figure when OMX runtime is available; otherwise mirror the same loop locally and record the skip reason.

## Workflow

1. Start with current PaperOrchestra session/status inspection unless purely reviewing a provided snippet. The figure skill must route back to the owning workflow (`$paperorchestra-plan`, `$paperorchestra-authoring-round`, `$paperorchestra-quality-gate`, or `$paperorchestra-live-review`) and must not become a parallel paper workflow.
2. Inspect the paper plan, section draft, or review finding.
3. Fill the Figure intent contract and write `figure-plan.<id>.md`.
4. Choose one-column vs two-column placement and `figure` vs `figure*`.
5. Build the Caption evidence map and reject/downgrade unsupported caption claims; weak caption rejected/downgraded is the correct outcome when the caption is not self-contained, not evidence-mapped, or stronger than the evidence.
6. Run Architect design before generation and write `figure-architect.<id>.json`; use native `architect` subagent/lane when available for new or replacement figures. Block if the Architect does not produce candidate designs, a selected design, rejected alternatives, visual hierarchy, and acceptance checks.
7. Choose output form:
   - deterministic vector/PDF/PNG/SVG render for exact-label scientific diagrams;
   - deterministic script/listing/table/plot asset for data, code, or case-study figures;
   - imagegen bitmap final for non-exact visual art only when venue policy allows;
   - imagegen concept/style reference + deterministic final asset for mixed paths;
   - LaTeX placement snippet only to embed the selected final asset;
   - caption only when the task is explicitly review-only and no new figure asset is requested.
8. Invoke imagegen for the selected role unless this is explicitly review-only/caption-only. Save the generated result into the PaperOrchestra workspace when the tool exposes a filesystem artifact; otherwise record the prompt, session/tool evidence, and the fact that no local image path was exposed. Do not move on with only a claim that imagegen ran.
9. Run Critic validation after Architect + imagegen evidence and write `figure-critic.<id>.json`; use native `critic` subagent/lane when available for new or replacement figures. Reinforce or redesign until the Critic verdict is non-blocking.
10. Render or generate the selected final asset. If imagegen bitmap art is final, save the selected output into the PaperOrchestra workspace and record it in `plot_assets.json` or the round artifact manifest. If using a deterministic path, render/export the exact-label final asset locally and record the source path, source SHA-256, final asset path, and final asset hash in `plot_assets.json`. If using a mixed path, save the imagegen prompt/result metadata as concept evidence and make the deterministic artifact the final authority.
11. Run visual-verdict/vision review on the final asset or rendered page and write `figure-visual-findings.<id>.json`; if it reports AI-artifact, readability, hierarchy, label-text, or publication-fit problems, repair/regenerate before continuing.
12. Draft the caption:
   - first sentence: what the figure shows;
   - second sentence: what claim it supports;
   - optional final sentence: key caveat or reading order.
13. Compile, write or refresh `figure-placement-review.json` from verified manuscript/template facts, run `paperorchestra visual-audit` on rendered pages, run/write `figure_gate.report.json`, and continue the Ralph loop until visual findings pass and the figure gate no longer blocks, or the issue becomes explicit `human_needed`.
14. Return an artifact card and route follow-up edits to the owning paper workflow.

## Review checklist

Check every figure for:

- claim alignment: does it support a stated paper claim?
- evidence alignment: are components grounded in code, experiments, sources, or plan artifacts?
- caption sufficiency: can the reader understand the figure if it floats?
- placement: does `figure` vs `figure*` match one-column/two-column readability?
- visual necessity: would prose or a table be clearer?
- imagegen participation: is there an imagegen prompt/result artifact or a blocking `prompt_only_no_image_generated` status?
- no invented components, citations, metrics, labels, or arrows; if imagegen introduces unsupported detail, reject or regenerate the asset.
- no AI-generated-artifact tells: garbled text, warped geometry, object bleeding, inconsistent lighting/shadows, fake UI chrome, or stock-art gloss.
- source-of-truth integrity: exact labels/data/arrows/code semantics have deterministic source paths and SHA-256 hashes.
- venue-policy safety: final imagegen art is used only when venue policy and disclosure allow it; unknown policy blocks imagegen final art for evidence-bearing exact figures.
- publication-fit: readable at final IEEE column/page width, no text below 8 pt equivalent, target 9--10 pt or larger, 3--4 semantic colors max, colorblind-safe semantics, enough whitespace, no faux-figure/list-with-icons smell.

## Final card

```text
Figure type:
Rhetorical job:
Figure message:
Supported claim:
Source evidence:
Output form:
Output-form gate verdict:
Venue AI policy:
Imagegen participation status:
Imagegen role:
Imagegen prompt:
Imagegen prompt artifact:
Imagegen result artifact or session evidence:
Imagegen concept evidence:
Source-of-truth artifact:
Source SHA-256:
Figure plan artifact:
Architect design artifact:
Critic validation artifact:
Generated image artifact:
Final asset artifact:
Final asset SHA-256:
Deterministic render script/hash:
Visual findings artifact:
Rendered-page/page-audit proof:
Ralph loop state / skip reason:
Recommended LaTeX environment:
Width target:
Caption draft:
Caption evidence map:
Self-contained/floating-caption check:
Weak-caption status:
Generation/edit artifact:
AI-artifact/publication QA verdict:
Readability/color verdict:
Risks/TODOs:
Next paper skill:
```
