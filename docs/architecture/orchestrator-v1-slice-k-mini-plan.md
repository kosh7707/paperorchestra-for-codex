# Slice K mini-plan — public-safe reference metadata preflight gate

Status: implemented; plan and implementation validated by Critic before commit
Date: 2026-05-13
Branch: `orchestrator-v1-runtime`

## 1. Target result

Before writing, inspect user-supplied reference metadata seeds and record a public-safe preflight gate:

```text
material path
-> material inventory/source digest
-> reference metadata audit
-> unknown/missing metadata blocker or pass summary
-> OrchestraState evidence_refs include reference_metadata_audit
```

This slice directly targets the failure mode where generated or imported references appear as `Unknown` or lack usable BibTeX metadata.

## 2. Reuse policy

Reuse existing repository parsing rather than creating a separate BibTeX parser:

- `paperorchestra.literature.load_prior_work_seed` for `.bib`/`.bibtex` seed normalization;
- existing unknown-value concepts from citation integrity, expressed locally as a small generic predicate if importing internals would couple too tightly.

This slice does not call Semantic Scholar, web search, providers, or OMX.

## 3. Public module and integration points

Proposed file:

```text
paperorchestra/orchestra_references.py
```

Types/functions:

```text
ReferenceMetadataEntry
ReferenceMetadataAudit
build_reference_metadata_audit(material_path)
```

Integrate conservatively with:

```text
paperorchestra/orchestrator.py
```

`run_until_blocked(..., material_path=...)` may append `reference_metadata_audit` evidence before claim/research planning. A failing audit should set or preserve `citations=unknown_refs` and add a blocker such as `reference_metadata_incomplete`, but it must not stop machine research routing.

## 4. Public-safe payload policy

Public payload may include:

- entry count;
- seed file count;
- per-entry redacted key label/hash;
- fields present/unknown field names;
- failing codes;
- private-safe summary flag.

Public payload must not include raw titles, raw author names, abstracts, raw BibTeX bodies, private paths, or private domain-specific tokens by default.

## 5. Gate policy

Status should be:

- `pass` when at least one metadata entry exists and required metadata is usable;
- `fail` when no metadata seed exists, no entries parse, or entries have unknown/missing title/author/year metadata.

This is a metadata preflight, not source-support verification. Passing this audit does not mean a citation supports a claim; it only means the engine has usable metadata to start research/citation support work.

## 6. Tests to add first

Proposed file:

```text
tests/test_orchestra_references.py
```

Minimum tests:

1. `.bib` material with title/author/year produces pass audit and redacted public entry;
2. `Unknown`/missing title-author-year fields produce fail audit and unknown-field codes;
3. no `.bib`/`.bibtex` seed produces fail audit;
4. public audit omits raw private marker titles/authors while preserving hashes;
5. `run_until_blocked(material_path=...)` records `reference_metadata_audit` before drafting and failing metadata sets `citations=unknown_refs` / blocker without replacing machine research routing.

## 7. Validation for this slice

Required before commit/push:

```bash
.venv/bin/python -m pytest tests/test_orchestra_references.py tests/test_orchestra_research_mission.py tests/test_orchestra_omx_invocation.py -q
.venv/bin/python -m pytest tests/test_orchestra_claims.py tests/test_orchestra_materials.py tests/test_orchestra_state_scenarios.py -q
.venv/bin/python -m pytest tests/test_orchestra_*.py tests/test_private_smoke_safety.py -q
git diff --check
```

Preferred:

```bash
.venv/bin/python -m pytest -q
scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
```

Critic plan validation is required before implementation. Critic implementation validation is required before commit.

Implementation evidence captured before commit:

- initial test run failed before implementation with missing `paperorchestra.orchestra_references`
- reference/research/OMX invocation targeted tests: passed
- claim/material/state targeted tests: passed
- orchestrator-family + private-smoke safety tests: passed
- full test suite: passed
- private leakage scan against local denylist: passed with zero matches
- Critic implementation verdict: APPROVE

## 8. Explicit non-goals

Slice K must not:

- verify claim support;
- mark citations as supported;
- fabricate missing BibTeX metadata;
- call S2/web/model providers;
- route missing metadata to `human_needed` before machine research/import work;
- leak raw private reference metadata in public state;
- use private/domain-specific reference rules.

## 9. Stop/replan triggers

Stop and replan if:

- public output needs raw title/author to pass tests;
- missing metadata blocks machine research routing entirely;
- passing metadata audit is treated as citation support;
- tests require private material;
- new parsing duplicates existing `literature.load_prior_work_seed` behavior unnecessarily.
