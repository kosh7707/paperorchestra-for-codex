---
name: paperorchestra-visual-audit
description: Render and inspect compiled PaperOrchestra PDFs at page-image level. Use when a manuscript needs visual/page layout audit, PDF screenshot review, table overflow checks, figure readability checks, one-column/two-column layout validation, cross-figure style consistency review, imported vision findings, or self-repair routing via visual_repair_brief.json.
---

# PaperOrchestra Visual Audit

## Invocation contract

Before executing any `$skill`, `omx`, `codex`, MCP, or PaperOrchestra CLI action from this skill, read `../paperorchestra/references/invocation-contract.md` and follow it. Required companion skills must be invoked, not merely recommended.

Use this skill after a manuscript has a compiled PDF or when a reviewer says the visual result cannot be judged from TeX alone. The goal is not final artwork generation; the goal is to create strong draft diagnostics and route repairable findings back into PaperOrchestra before bothering the author.

## Core contract

A visual audit must keep this loop intact:

```text
compiled PDF -> rendered page images -> contact sheet -> visual findings -> page-layout-review.json -> visual_repair_brief.json -> visual_repair_candidate.json -> bounded repair -> recompile -> rerender
```

Never mark a visual review as passed from TeX-only evidence. If no vision/human findings are imported, record `visual_review_pending` and route to a reviewer instead of claiming success.

## What to inspect

Check rendered pages for issues TeX/source review cannot reliably see:

- table overflow, clipped columns, unreadable dense cells;
- figure readability, tiny labels, low contrast, bad crop, bad aspect ratio;
- float clumps, orphaned headings, column imbalance, excessive whitespace;
- one-column vs two-column placement mistakes (`figure` vs `figure*`, table width, caption float risk);
- cross-document visual consistency: figure palette, line weights, typography, diagram density, caption style;
- generated draft artwork still used as if it were final evidence.

For every finding, preserve claim/location/caption coupling:

```text
visual issue:
supported manuscript claim affected:
page/location:
figure/table/caption affected:
why this position matters:
repair candidate:
acceptance check after rerender:
```

## Command surface

Preferred source/MCP tool:

```text
visual_audit(cwd=..., pdf=..., render_dir=..., findings_json=..., output=...)
```

CLI equivalent, only when the current installed/source command surface verifies it with `paperorchestra visual-audit --help` or `python -m paperorchestra.cli visual-audit --help`:

```bash
paperorchestra visual-audit --pdf compiled.pdf --render-dir rendered-pages
paperorchestra visual-audit --pdf compiled.pdf --findings-json page-visual-findings.json
```

If neither command exists, do not invent a CLI fallback. Use the attached MCP/source tool if visible, or block with the missing command named and route to `$paperorchestra-quality-gate` / `$paperorchestra-figure` only for non-rendered evidence checks.

The command writes:

- `page-layout-review.json`: render status, page images, contact sheets, imported findings, failure/warning codes, repair candidates.
- `page-contact-sheet.html` and `page-contact-sheet.md`: reviewer entry points over every rendered page image.
- `visual_repair_brief.json` during QA repair when visual findings are machine-actionable.
- `visual_repair_candidate.json` after the brief, with concrete bounded TeX/table/figure repair strategies and claim/location/caption guards before author handoff.

Imported findings should use this compact schema:

```json
{
  "schema_version": "page-visual-findings/1",
  "reviewer": "visual-verdict|vision-agent|human|codex-subagent",
  "page_findings": [
    {"page": 2, "code": "table_overflow", "severity": "fail", "target": "Table 2", "detail": "...", "suggested_fix": "..."}
  ],
  "document_findings": [
    {"code": "visual_style_inconsistent", "severity": "warn", "target": "figures", "detail": "...", "suggested_fix": "..."}
  ]
}
```

## OMX companion routing

- `$visual-verdict`: use for page screenshots/contact sheets that need visual QA, especially before importing `page-visual-findings.json`.
- `$ultrawork`: use when multiple independent visual reviewers can inspect different page ranges, figures, tables, or one-column/two-column variants.
- `$ralph`: use when visual findings should continue through repair, recompile, rerender, and re-audit until a bounded stop condition.
- `$paperorchestra-figure`: use when a finding concerns figure intent, caption evidence map, output form, or final artwork replacement.
- `$paperorchestra-quality-gate`: use after `page-layout-review.json` or `visual_repair_brief.json` changes to decide continue vs human_needed.

## Repair policy

Classify before handoff:

- `automatic`: missing/stale page layout review or render evidence failure; rerun a verified visual-audit MCP/source/CLI path after render prerequisites are restored.
- `semi_auto`: table overflow, unreadable figure, float clump, heading orphan, column imbalance, excessive whitespace, visual style inconsistency, visual review pending. Generate `visual_repair_brief.json`, then `visual_repair_candidate.json`; let PaperOrchestra/Critic propose a bounded candidate before author handoff and rerun the audit after adoption.
- `human_needed`: final artwork replacement, semantic visual evidence dispute, aesthetic preference, or adoption/rejection of an already prepared repair candidate. Give the author exact decisions/artifacts needed; do not say only “the picture is bad.”

A repair candidate is acceptable only if:

- it preserves or weakens the affected manuscript claim rather than strengthening it;
- the figure/table still appears at a defensible rhetorical location;
- the caption remains accurate and self-contained after the visual change;
- the one-column/two-column environment is readable after rerender;
- a fresh page-layout review no longer reports the same issue.

## Final card

```text
PDF:
Render status:
Contact sheet:
Imported findings:
Failing codes:
Warning codes:
Repair brief:
Repair candidate:
Self-repair owner:
Human-needed decisions:
Next skill:
```
