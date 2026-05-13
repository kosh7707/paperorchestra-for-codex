# Slice AC mini-plan — citation quality gate hardening

Status: revised mini-plan requiring Critic re-validation before tests or implementation
Date: 2026-05-13
Branch: `orchestrator-v1-runtime`
Scope: public, domain-general citation quality hardening. Do not include private smoke material, private-domain terms, or domain-specific citation heuristics.

## 0. Pre-plan issue check

Required by the post-Z workflow plan before every slice mini-plan:

```bash
gh issue list --state open --json number,title,labels,updatedAt,url --limit 50
# []
```

No actionable open GitHub issue blocked Slice AC planning.

## 1. Target result

Private final-smoke feedback exposed a severe generic failure mode: a manuscript
can look structurally complete while many rendered references are `Unknown`, weak,
duplicated, over-cited, or not actually supporting the cited sentence. Slice AC
must harden this as a **general-purpose citation quality gate**, not a
private-domain special case.

Slice AC separates and records three concerns:

1. **citation need** — which critical claims/sentences require citation support;
2. **citation support** — whether the cited source supports that claim/sentence;
3. **citation metadata** — whether visible/rendered references identify real,
   non-`Unknown` sources.

The result should be a public-safe artifact and CLI surface that can block
claim-safe readiness when critical citation failures remain, while leaving
non-critical over-citation/duplicate issues as warnings where appropriate.

## 2. Current baseline

Existing useful surfaces:

- `paperorchestra/citation_integrity.py`
  - `build_rendered_reference_audit` detects visible `Unknown` metadata and missing BibTeX keys;
  - `build_citation_source_match` binds `citation_support_review.json` into source-match status;
  - `build_citation_integrity_audit` detects citation bombs, duplicate support,
    source mismatch, and context-policy violations;
  - `citation_integrity_check` participates in claim-safe quality-loop Tier 2.
- `paperorchestra/orchestra_claims.py`
  - builds public-safe claim/evidence/citation obligations from material.
- `paperorchestra/orchestra_references.py`
  - audits user-supplied reference metadata seeds before research.
- `tests/test_citation_integrity.py`, `tests/test_citation_support_provenance.py`,
  and `tests/test_orchestra_references.py` already cover important lower-level checks.

Observed gaps to close without overfitting:

- no single public-safe citation quality artifact maps need/support/metadata into
  hard-gate status;
- critical vs non-critical citation failures are not made explicit enough for
  acceptance gates `no_unknown_refs_for_critical_claims` and `citation_integrity`;
- support review records may contain raw sentence text and should be summarized
  by hashes/labels in the new public gate;
- machine-solvable citation/source gaps must keep routing to research/OMX, not
  `human_needed`;
- existing `citation_intent_plan` is a derived diagnostic surface. AC must not
  introduce a rigid author-authored citation-intent planning workflow.

## 3. Proposed implementation boundary

Add a small deterministic gate module, likely:

```text
paperorchestra/orchestra_citation_quality.py
```

Proposed public constants/types:

```text
CITATION_QUALITY_GATE_SCHEMA_VERSION = "citation-quality-gate/1"
CitationQualityItem
CitationQualityGateReport
build_citation_quality_gate(cwd, *, quality_mode="ralph")
write_citation_quality_gate(cwd, *, quality_mode="ralph", output_path=None)
```

Default artifact path/helper:

```text
citation_quality_gate_path(cwd) -> artifact_path(cwd, "citation_quality_gate.json")
```

Exact input priority/order:

1. current session and `state.artifacts.paper_full_tex`;
2. `citation_support_review.json` located next to `paper.full.tex`;
3. `rendered_reference_audit.json`;
4. `citation_source_match.json`;
5. `citation_integrity.audit.json`;
6. `state.artifacts.claim_map_json`;
7. `state.artifacts.citation_placement_plan_json`;
8. claim-graph evidence refs in `state.evidence_refs` when present;
9. `reference_metadata_audit` evidence refs in `state.evidence_refs` when present.

Missing manuscript behavior:

- Library builder returns a deterministic fail report with code
  `citation_quality_manuscript_missing` and no items.
- CLI command prints JSON/nonzero only if the current session itself cannot be
  loaded; a loaded session with missing manuscript writes a fail artifact so QA can
  inspect the reason.

The report consumes existing artifacts when present but never embeds them raw:

- rendered reference audit;
- citation support review;
- citation source match;
- citation integrity audit;
- claim graph / claim map / citation placement plan when present;
- reference metadata audit when produced during orchestrator material inspection.

The report should be conservative if evidence is missing in `claim_safe` mode:
missing support/metadata evidence for a critical citation is a fail, not a pass.
Outside `claim_safe`, missing derived artifacts may remain warning/skipped if the
current lower-level gate already permits that mode.

## 4. Criticality derivation contract

The new gate must derive criticality from existing public-safe artifact fields only.
A citation item/key/claim is critical if any of the following public signals apply:

1. support-review item has `critical=true`;
2. support-review item has `claim_type`, `criticality`, `citation_role`, or
   `support_role` in a high-criticality set: `critical`, `high`, `root`,
   `central_support`, `numeric`, `comparative`, `security`, `novelty`, `causal`,
   `benchmark`, `result`;
3. claim map entry linked to the citation key has `required=true`,
   `citation_required=true`, or `required_source_type` in
   `external_literature`, `standard`, `benchmark_reference`, `prior_work`;
4. claim map entry linked to the citation key has high-criticality `claim_type`
   or `graph_role`;
5. claim-graph citation obligation linked to the claim/key is `critical=true`;
6. no direct claim/key linkage exists, but `claim_safe` mode sees a rendered
   visible key with unknown/missing metadata and no support evidence. This is
   conservatively treated as critical until support review proves otherwise.

A key can be non-critical only when explicit public signals classify it as
background/local/optional and no critical signal applies. The tests must include
the same `Unknown` key shape in critical and non-critical contexts to prove
blocker vs warning behavior.

## 5. Public schema contract

The new artifact should include only public-safe summaries:

```json
{
  "schema_version": "citation-quality-gate/1",
  "status": "pass | warn | fail",
  "quality_mode": "draft | ralph | claim_safe",
  "manuscript_sha256": "...",
  "hard_gate_failures": ["critical_unknown_reference"],
  "warning_codes": ["noncritical_duplicate_reference"],
  "counts": {
    "critical_need_count": 0,
    "critical_unknown_reference_count": 0,
    "critical_unsupported_count": 0,
    "citation_bomb_count": 0,
    "duplicate_reference_count": 0
  },
  "items": [
    {
      "item_id": "redacted-citation-item:...",
      "claim_id": "C1",
      "citation_keys_sha256": ["..."],
      "critical": true,
      "need_status": "required | optional | unknown",
      "support_status": "supported | unsupported | contradicted | metadata_only | insufficient_evidence | unknown",
      "metadata_status": "known | unknown | missing",
      "severity": "blocker | warning | info",
      "failing_codes": ["critical_unsupported_citation"],
      "private_safe": true
    }
  ],
  "private_safe_summary": true
}
```

The new report must summarize reused/lower-level artifacts by hashes, statuses,
counts, and redacted labels only. It must never embed lower-level raw fields such
as `checks`, `sentence`, `source_artifacts.path`, title/author values, provider
trace payloads, or absolute artifact paths.

The artifact must not include:

- raw sentence text;
- raw title/author/reference metadata;
- raw prompts or provider outputs;
- absolute workspace/temp paths;
- private markers;
- private-domain terms;
- generated manuscript prose excerpts.

Allowed:

- citation keys only as hashes or stable redacted labels;
- claim IDs and obligation IDs already public-safe;
- artifact SHA-256 values;
- bounded code/status strings;
- relative artifact references if already public-safe.

## 6. Gate semantics

### 6.1 Hard blockers

In `claim_safe` mode, the new report must `fail` for:

- critical citation need with no support evidence;
- critical visible reference with missing BibTeX entry;
- critical visible reference with `Unknown`/empty title, author/organization, or year/date;
- support status `unsupported`, `contradicted`, `metadata_only`, or
  `insufficient_evidence` for critical claims;
- stale/unbound citation evidence for the current manuscript;
- citation context-policy violation for own contributions or required external
  literature claims.

### 6.2 Warnings / non-critical issues

The report may `warn` instead of fail for:

- duplicate reference use when multiple distinct roles/claims justify reuse;
- non-critical metadata gaps outside `claim_safe`;
- citation density concerns that require human/source-use judgment but do not
  hide critical `Unknown`/unsupported support.

### 6.3 Over-citation and duplicates

Reuse existing citation bomb and duplicate support logic where possible. AC should
make the result easier to consume in one gate artifact, not fork a second policy
with different thresholds.

### 6.4 Machine-solvable before human-needed

Critical citation/source gaps route to research/citation support work before
`human_needed`. AC must add regression coverage that unknown/unsupported critical
citations keep readiness blocked and produce `start_autoresearch` or
`start_autoresearch_goal` where the orchestrator/action planner already owns that
routing.

## 7. Integration points

Required integration:

1. Add CLI command, likely:

   ```bash
   paperorchestra audit-citation-quality --quality-mode claim_safe [--output path]
   ```

2. Integrate the new gate into claim-safe quality checks with exact key
   `citation_quality_gate` under Tier 2 (`tier_2_claim_safety.checks`). The
   gate's `hard_gate_failures` must be propagated into Tier 2 `failing_codes`
   with stable code prefix or exact codes such as:

   ```text
   critical_unknown_reference
   critical_missing_bib_entry
   critical_unsupported_citation
   critical_citation_support_missing
   citation_quality_stale
   citation_quality_manuscript_missing
   ```

   Existing `citation_integrity_gate` remains present and green/broken according
   to its current contract; AC adds a stricter aggregate gate rather than
   deleting existing artifacts.

3. Update `quality_loop_plan_logic` so new critical citation-quality codes route
   to machine-solvable refresh/research/citation-support actions first
   (`automation=automatic` or `semi_auto`), not `automation=human_needed`.
   Human-needed remains valid only for final source-use judgment after machine
   support evidence exists.

4. Ensure acceptance-ledger gates can cite this artifact later:
   - `no_unknown_refs_for_critical_claims`;
   - `citation_integrity`.

Non-goal for AC: automatic population of the full acceptance ledger. That remains
final audit work unless it is trivial and separately tested.

## 8. Tests to add first

### New/updated unit tests

Add `tests/test_orchestra_citation_quality.py` before implementation.

Minimum failing tests:

1. A rendered visible critical reference with `Unknown` metadata fails
   `claim_safe` with `critical_unknown_reference` and contributes to
   `no_unknown_refs_for_critical_claims` evidence.
2. A citation support item for a critical claim with `unsupported` or
   `metadata_only` fails with `critical_unsupported_citation`.
3. A supported critical citation with known rendered metadata passes the hard
   blockers.
4. Non-critical duplicate/over-citation produces warnings but does not mask a
   critical blocker.
5. Duplicate use across distinct roles/claims is not flagged as a hard failure.
6. Missing citation support evidence for a critical need fails in `claim_safe`.
7. Public report JSON omits raw sentence text, raw title/author metadata, absolute
   paths, private markers, and private-domain terms.
8. The report is manuscript-bound and stale artifacts fail or warn according to
   `quality_mode`.
9. Machine-solvable citation gaps do not become `human_needed`; existing
   orchestrator/action planner state remains research-routed.
10. The same unknown metadata key is a blocker when linked to a critical claim
    and only a warning when explicitly linked to non-critical/background use.
11. Full rendered JSON scan over the new citation-quality report and
    `quality-eval` / quality-loop payload omits raw sentences, raw lower-level
    paths, raw metadata, provider traces, absolute paths, private markers, and
    private-domain terms.
12. New quality-loop plan actions for critical citation-quality codes use
    automatic/semi-auto machine work before any human-needed source-use judgment.

### Existing tests that must remain green

```bash
.venv/bin/python -m pytest tests/test_citation_integrity.py \
  tests/test_citation_support_provenance.py \
  tests/test_orchestra_references.py \
  tests/test_orchestra_claims.py -q
```

### CLI / quality-loop tests

Add or update tests proving:

- `paperorchestra audit-citation-quality --quality-mode claim_safe --output ...`
  writes the artifact;
- claim-safe quality evaluation includes the new gate failure code;
- existing `audit-citation-integrity` and `audit-citation-integrity-critic`
  continue to function.

## 9. Explicit non-goals

Slice AC must not:

- call live S2/web/model/search or require network access;
- fabricate citation metadata, BibTeX, titles, authors, years, or support status;
- create a new author-authored citation-intent workflow;
- mark readiness pass from warning/pass while any hard critical citation blocker
  remains;
- remove or rename existing `audit-rendered-references`,
  `audit-citation-integrity`, `audit-citation-integrity-critic`, or
  `review-citations` commands;
- introduce private-domain-specific terms, fixtures, or heuristics.

## 10. Validation before implementation commit

Local:

```bash
.venv/bin/python -m pytest tests/test_orchestra_citation_quality.py -q
.venv/bin/python -m pytest tests/test_citation_integrity.py \
  tests/test_citation_support_provenance.py \
  tests/test_orchestra_references.py \
  tests/test_orchestra_claims.py -q
.venv/bin/python -m pytest tests/test_orchestrator_omx_entrypoints.py \
  tests/test_orchestrator_cli_entrypoints.py \
  tests/test_orchestrator_mcp_entrypoints.py -q
.venv/bin/python -m pytest -q
scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
grep -RIn "<private-domain literal>" $(git ls-files 'docs/**' 'paperorchestra/**' 'tests/**' 'skills/**' 'README.md' 'ENVIRONMENT.md') || true
git diff --check
```

Critic implementation validation is required before commit/push.

## 11. Container proof after push

After implementation commit is pushed, run a fresh container proof at least over
citation-gate tests and the orchestration entrypoint tests impacted by routing:

```bash
docker run --rm paperorchestra-ubuntu-tools:24.04 bash -lc 'set -euo pipefail; \
  git clone --quiet https://github.com/kosh7707/paperorchestra-for-codex.git repo; \
  cd repo; \
  git checkout --quiet orchestrator-v1-runtime; \
  python3 -m venv .venv; \
  . .venv/bin/activate; \
  python -m pip install --quiet -e ".[dev]"; \
  python -m pytest tests/test_orchestra_citation_quality.py \
    tests/test_citation_integrity.py \
    tests/test_orchestra_references.py \
    tests/test_orchestrator_cli_entrypoints.py \
    tests/test_orchestrator_mcp_entrypoints.py -q'
```

Record proof in this plan or a follow-up evidence commit.

## 12. Stop/replan triggers

Stop and replan if:

- the gate requires private raw claim/sentence/reference text in public artifacts;
- the implementation introduces private-domain-specific heuristics or fixtures;
- the new gate contradicts existing `citation_integrity_check` semantics rather
  than tightening them through tested integration;
- `human_needed` is used for machine-solvable citation/source lookup;
- high citation quality score or warning status can override a hard critical
  citation blocker;
- removing or renaming existing citation artifacts would break documented CLI
  commands without a migration plan.

## 13. Local implementation evidence

Implementation completed on 2026-05-13 after failing-test-first iteration.

Failing evidence before implementation/fix:

- Initial AC tests failed with `ModuleNotFoundError` for
  `paperorchestra.orchestra_citation_quality`.
- First implementation exposed missing contracts:
  - public-safe scan was too broad and treated `private_safe_summary` keys as
    private markers;
  - CLI test used a non-existent global `--cwd`;
  - quality-eval test did not satisfy upstream planning/citation preconditions;
  - Critic found that a critical supported citation could pass claim-safe when
    `rendered_reference_audit.json` was missing.

Passing evidence after fixes:

```bash
.venv/bin/python -m pytest tests/test_orchestra_citation_quality.py -q
# 13 passed

.venv/bin/python -m pytest tests/test_citation_integrity.py \
  tests/test_citation_support_provenance.py \
  tests/test_orchestra_references.py \
  tests/test_orchestra_claims.py \
  tests/test_orchestra_citation_quality.py -q
# 36 passed

.venv/bin/python -m pytest tests/test_orchestrator_omx_entrypoints.py \
  tests/test_orchestrator_cli_entrypoints.py \
  tests/test_orchestrator_mcp_entrypoints.py \
  tests/test_quality_gate.py -q
# 46 passed, 5 subtests passed

.venv/bin/python -m pytest -q
# 931 passed, 177 subtests passed

git diff --check
# ok

scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
# match_count: 0
```

Critic implementation validation:

- First pass: `CHANGES_REQUIRED`; fail claim-safe when rendered metadata evidence
  is missing for a critical citation, and avoid adding absolute citation-quality
  paths to quality-eval.
- Second pass: `APPROVE`; direct OrchestratorState evidence-ref consumption is
  not a blocker for AC because the public API is session-artifact based and
  remains conservative when persisted support/metadata evidence is missing.
