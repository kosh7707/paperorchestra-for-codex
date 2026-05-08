# PaperOrchestra Boundary Contracts

## Purpose

This document fixes the tranche-1 boundary contract for PaperOrchestra's authoring pipeline. The central rule is:

> Machine/control text may be stored for orchestration and validation, but it must not be shown to writer/refiner models as authorial obligations and must not be inserted into manuscript prose.

This contract is intentionally narrower than a full architecture rewrite. It covers the current leak path: planning generation (`narrative.py`) → writer/refiner prompt projection and manuscript insertion (`pipeline.py`) → validation (`validator.py`).

## Stable public facades

Tranche 1 must preserve these callable facades and CLI-facing behaviors unless a change is separately classified as an intended smoke-follow-up:

- `paperorchestra.validator.validate_manuscript`
- `paperorchestra.quality_loop.write_quality_eval`
- `paperorchestra.quality_loop.write_quality_loop_plan`
- `paperorchestra.ralph_bridge.build_qa_loop_brief`
- `paperorchestra.ralph_bridge.run_qa_loop_step`
- CLI commands that exercise them, including `validate-current`, `quality-eval`, and `qa-loop-plan`

## Artifact compatibility

The following artifacts remain at the same paths and retain required legacy fields:

- `narrative_plan.json`
- `claim_map.json`
- `citation_placement_plan.json`

Byte-for-byte identity is not required. Required existing fields remain present and semantically compatible, including `claims[*].text`, `coverage_terms`, `coverage_groups`, `section_roles[*].must_cover`, and `story_beats[*].beat`. Additional helper fields/artifacts are allowed only when non-breaking.

## Boundary projection

Writer, manuscript, and validator code must consume a shared normalized projection rather than independently interpreting raw `claim["text"]`.

The projection conceptually separates:

- `machine_obligation`: internal-only instruction for orchestration, validation, or repair.
- `authorial_claim`: scholarly prose that may be shown to writer/refiner models.
- `scope_note`: scholarly prose that may be inserted into a manuscript.
- `coverage_terms` / `coverage_groups`: deterministic validation terms.

## Allowed writer-visible inputs

Writer/refiner models may see:

- authorial claims,
- safe scope/limitation phrasing,
- verified citation keys and metadata selected for the prompt,
- section roles stated as scholarly goals,
- coverage cues phrased as ordinary paper obligations.

They must not see:

- claim IDs, source hashes, or source references as prose obligations,
- `claim_map.json`, `narrative_plan.json`, or `author_facing_writer_brief.json` as manuscript concepts,
- artifact-style labels for authoring briefs; use neutral prompt block names such as `scholarly_authoring_brief`,
- outline/search-planning field names such as `hook_hypothesis`, `search_directions`, or `*_mission` in writer-visible planning payloads,
- prompt/control instructions as required manuscript content,
- source-boundary/process guardrail phrases such as “the draft must preserve,” “benchmark narrative must report,” or “does not add an external claim.”

## Allowed manuscript-insertable text sources

Deterministic manuscript insertion helpers may use only:

- validated `scope_note` text from the normalized projection, or
- generic type-based authorial prose generated from safe claim fields.

They must not prefix or copy arbitrary raw `claim["text"]` when that field resembles machine/control prose. Generic input-note sections such as claim-boundary or author-note headings are control sections: cleanup should remove them from manuscripts and validators should flag them if they survive.

## Validator boundary

Validators remain safety nets, not the primary boundary. They may consume normalized coverage projections internally while preserving public issue codes and facade signatures. They should not encourage control sentences as the only way to express coverage requirements.

## Behavior-change classification

Every behavior change found during this refactor must be classified as one of:

1. **Refactor drift** — accidental behavior change; fix back to original behavior.
2. **Intended smoke-follow-up** — purposeful product improvement already tied to prior smoke findings; isolate and test it.
3. **Unclear public contract change** — do not silently ship; escalate in execution report.

## Tranche discipline

Tranche 1 scope is `narrative.py`, `pipeline.py`, and `validator.py` boundary sealing plus tests/docs. `quality_loop.py` and `ralph_bridge.py` should remain consumers behind stable facades unless a minimal compatibility touch is necessary.
