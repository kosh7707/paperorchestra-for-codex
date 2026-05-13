# Slice G mini-plan — generic material inventory and source digest skeleton

Status: implemented; plan and implementation validated by Critic before commit
Date: 2026-05-13
Branch: `orchestrator-v1-runtime`

## 1. Target result

Turn a user-provided material path into public-safe, generic intake evidence:

```text
material path
-> material inventory
-> source digest skeleton
-> OrchestraState material/source_digest facets
-> next action: build_claim_graph or request missing material
```

This slice is deterministic and local. It does not call LLMs, web search, OMX, or private reference logic.

## 2. Public module and integration points

Proposed file:

```text
paperorchestra/orchestra_materials.py
```

Types/functions:

```text
MaterialFile
MaterialInventory
SourceDigest
build_material_inventory(path)
build_source_digest(inventory)
```

Integrate conservatively with:

```text
paperorchestra/orchestrator.py
```

`inspect_state(..., material_path=...)` may now build inventory/digest when the path exists and set:

- `material=inventoried_sufficient` if enough generic source files exist;
- `material=inventoried_insufficient` if not;
- `source_digest=ready` when digest exists;
- `source_digest=blocked` if material is insufficient.

## 3. Generic sufficiency policy

Sufficient material requires at least two source-like text files or one LaTeX manuscript plus one supporting text/BibTeX-like file.

Recognized roles are generic:

```text
manuscript_tex
bibtex
idea_or_notes
experiment_or_results
venue_or_guidelines
figure_asset
other_text
other_binary
```

No domain-specific filenames or private-specific terms are allowed.

## 4. Public-safe digest policy

The digest may include:

- file counts;
- extension counts;
- role counts;
- total bytes;
- hashes;
- short safe snippets from public/synthetic tests only when explicitly requested.

Default digest must avoid raw private contents. It should include `private_safe_summary=true`.

## 5. Tests to add first

Proposed file:

```text
tests/test_orchestra_materials.py
```

Minimum failing tests before implementation:

1. inventory classifies generic `.tex`, `.bib`, `.md`, `.pdf` files into roles;
2. inventory records hashes and counts without raw content;
3. source digest marks sufficient material for generic manuscript + bibliography + notes;
4. source digest marks insufficient material for a single tiny note;
5. `inspect_state(material_path=...)` sets `inventoried_sufficient` and `source_digest=ready` for sufficient synthetic material;
6. insufficient material keeps drafting blocked and plans `provide_material` or `inspect_material`/missing-material guidance;
7. public-safe digest does not include raw synthetic private marker content;
8. no private/domain-specific filename assumptions appear.

## 6. Validation for this slice

Required before commit/push:

```bash
.venv/bin/python -m pytest tests/test_orchestra_materials.py tests/test_orchestrator_cli_entrypoints.py tests/test_orchestrator_mcp_entrypoints.py -q
.venv/bin/python -m pytest tests/test_orchestra_*.py tests/test_private_smoke_safety.py -q
.venv/bin/python -m pytest tests/test_mcp_server.py tests/test_pre_live_check_script.py -q
git diff --check
```

Preferred:

```bash
.venv/bin/python -m pytest -q
```

Critic implementation validation is required before commit.

Implementation evidence captured before commit:

- targeted orchestrator/material tests: passed
- orchestrator family + private-smoke safety tests: passed
- MCP/pre-live smoke tests: passed
- full test suite: passed
- private leakage scan against local denylist: passed with zero matches
- Critic implementation verdict: APPROVE

## 7. Explicit non-goals

Slice G must not:

- parse scientific claims deeply;
- build validated claim graphs;
- call live models/search/OMX;
- use private/domain-specific names;
- expose raw private text by default;
- write manuscript prose.

## 8. Stop/replan triggers

Stop and replan if:

- sufficiency policy needs domain-specific filenames;
- digest includes raw private content by default;
- inspect_state starts claiming evidence/claims are validated merely from inventory;
- private material is copied into the repo;
- tests require actual private material.
