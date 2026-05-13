# Slice AG mini-plan — fresh/private final-smoke acceptance summary

Status: draft mini-plan requiring Critic validation before tests or implementation
Date: 2026-05-14
Branch: `orchestrator-v1-runtime`
Scope: public, domain-general fresh-smoke harness summarization and redacted acceptance evidence. Do not include private smoke material, private-domain terms, raw private paths, or private figure/reference names.

## 0. Pre-plan issue check

Required by the post-Z workflow plan before every slice mini-plan:

```bash
gh issue list --state open --json number,title,labels,updatedAt,url --limit 50
# []
```

No actionable open GitHub issue blocked Slice AG planning.

## 1. Target result

Slice AG turns the existing fresh full live smoke wrapper into a public-safe final
acceptance surface. The product already has scripts for private material prep,
material invariance, full smoke execution, evidence completeness, Lane-A
validation, operator feedback, and leakage scans. What is still missing is a
single redacted summary/evidence producer that maps a fresh-smoke evidence bundle
to acceptance-ledger gate evidence without leaking private material or overclaiming
submission readiness.

AG must support two modes:

1. **Public synthetic/container proof** — test the summarizer and validation logic
   with synthetic evidence fixtures in CI/container.
2. **Private final live smoke evidence** — consume a real evidence root generated
   outside the repo from private material and emit only hashes/counts/status codes
   in public evidence.

AG does **not** run the long private live smoke inside unit tests, and product code
must not embed private material assumptions.

## 2. Current baseline

Existing surfaces:

- `scripts/fresh-full-live-smoke-loop.sh`
  - owns long-running fresh full live smoke orchestration;
  - accepts `--evidence-root`, `--material-root`, `--expected-material-root`,
    `--max-operator-cycles`, and retry/runtime settings;
  - records redacted logs, verdict JSON, material invariance, evidence
    completeness, Lane-A, critic, operator-feedback, and artifact manifest data.
- `paperorchestra/fresh_smoke.py`
  - `validate_material_invariance(...)`;
  - `validate_fresh_smoke_verdict(...)`;
  - `validate_evidence_completeness(...)`;
  - `build_fresh_smoke_artifact_manifest(...)`;
  - operator feedback normalization helpers.
- `scripts/prepare-private-smoke-materials.py`
  - extracts private zip material outside repo and emits redacted manifest.
- `scripts/check-private-leakage.py`
  - tracked/explicit path private-denylist scanner.
- `tests/test_private_smoke_safety.py` and `tests/test_fresh_smoke_inputs.py`
  - cover private prep, leakage scanner, and input derivation safety.

Gaps:

- no single function/CLI converts an evidence root into acceptance-ledger evidence
  for AG-related gates;
- no public-safe summary that states which final-smoke acceptance predicates pass,
  block, or fail;
- no tests proving final-smoke summary refuses forbidden raw verdicts such as
  `submission_ready` or `ready_for_human_finalization`;
- no tests proving public summary excludes raw evidence root/material root paths;
- no tests proving private final live smoke evidence can be recorded as redacted
  hashes/counts only.

## 3. Implementation boundary

Add a summarizer module rather than rewriting the long smoke runner:

```text
paperorchestra/fresh_smoke_acceptance.py
  FRESH_SMOKE_ACCEPTANCE_SCHEMA_VERSION = "fresh-smoke-acceptance-summary/1"
build_fresh_smoke_acceptance_summary(evidence_root, *, material_manifest=None) -> dict
build_fresh_smoke_acceptance_summary(
  evidence_root,
  *,
  smoke_mode="synthetic_container" | "private_final",
  material_manifest=None,
) -> dict
fresh_smoke_acceptance_evidence(summary) -> dict
write_fresh_smoke_acceptance_summary(evidence_root, *, output_path=None, smoke_mode="synthetic_container", material_manifest=None) -> tuple[Path, dict]
```

CLI addition:

```bash
paperorchestra summarize-fresh-smoke \
  --evidence-root DIR \
  --smoke-mode synthetic_container|private_final \
  [--material-manifest PATH] [--output PATH] [--json]
```

MCP addition:

```text
summarize_fresh_smoke(cwd?, evidence_root, smoke_mode?, material_manifest?, output?)
```

The summarizer consumes existing validation functions. It does not launch Docker,
Codex, OMX, live models, web search, compile, or the smoke loop itself.

## 4. Public schema contract

Output shape:

```json
{
  "schema_version": "fresh-smoke-acceptance-summary/1",
  "smoke_mode": "synthetic_container | private_final",
  "overall_status": "pass | blocked | fail",
  "evidence_root_label": "redacted-evidence-root:...",
  "material_manifest_label": "redacted-material-manifest:...",
  "checks": [
    {"id": "evidence_completeness", "status": "pass|blocked|fail", "reason": "..."},
    {"id": "fresh_smoke_verdict", "status": "pass|blocked|fail", "reason": "..."},
    {"id": "material_invariance", "status": "pass|blocked|fail", "reason": "..."},
    {"id": "meta_leakage_scan", "status": "pass|blocked|fail", "reason": "..."},
    {"id": "operator_feedback_cycles", "status": "pass|blocked|fail", "reason": "..."},
    {"id": "exported_pdf_tex_evidence", "status": "pass|blocked|fail", "reason": "..."}
  ],
  "redacted_counts": {
    "operator_feedback_cycles": 0,
    "artifact_file_count": 0,
    "material_file_count": 0
  },
  "acceptance_evidence": {"...": "..."},
  "private_safe_summary": true
}
```

Overall status rules:

- `fail` if any check fails;
- else `blocked` if any check is blocked;
- else `pass`.

Check rules:

1. `evidence_completeness`
   - `pass`: `validate_evidence_completeness(evidence_root).status == "pass"`.
   - `blocked`: required evidence is missing/incomplete.
   - `fail`: evidence exists but is inconsistent, malformed, unsafe, or verdict
     validation fails.
2. `fresh_smoke_verdict`
   - `pass`: `readable/verdict.json` validates via `validate_fresh_smoke_verdict`
     and uses an allowed smoke verdict such as `pass_loop_verified`.
   - `blocked`: verdict file is missing or the loop stopped before final evidence.
   - `fail`: verdict uses forbidden/raw loop/submission states such as
     `success`, `submission_ready`, `camera_ready`, `human_needed`,
     `ready_for_human_finalization`, `continue`, `failed`, or `execution_error`.
3. `material_invariance`
   - `pass`: `artifacts/material-invariance.json.status == "pass"`.
   - `blocked`: material invariance artifact is missing.
   - `fail`: material invariance artifact reports mismatch/fail.
4. `meta_leakage_scan`
   - `pass`: `artifacts/meta-leakage-scan.json.status in {"pass", "ok"}` and
     match count is zero when present.
   - `blocked`: meta leakage scan is missing.
   - `fail`: scan reports blocked/fail or nonzero matches.
5. `operator_feedback_cycles`
   - `pass`: verdict reports at least one operator/human_needed cycle when the
     terminal state required it; cycle split counters are internally consistent;
     attempted cycles are at or below the enforced maximum of 5.
   - `blocked`: loop did not reach a state where operator cycles are known.
   - `fail`: cycle counters contradict the verdict/history, attempted cycles
     exceed 5, or terminal `human_needed` evidence is required but missing.
6. `exported_pdf_tex_evidence`
   - `pass`: artifact manifest or evidence bundle contains exported PDF, TeX, and
     evidence summary artifacts.
   - `blocked`: output artifacts are not produced yet.
   - `fail`: artifact manifest contradicts itself or references missing artifacts.

Acceptance evidence mapping:

`fresh_smoke_acceptance_evidence(summary)` returns a mapping directly consumable
by `build_acceptance_ledger`, covering at least these gate IDs:

- `fresh_container_functional_smoke`
- `private_final_live_smoke_redacted`
- `private_leakage_scan`
- `compile_export`
- `exported_pdf_tex_evidence_bundle`

Each entry uses only allowed evidence refs: `kind`, `summary`, workspace-relative
or redacted `path`, and optional 64-hex `sha256`.

Exact status mapping:

| Acceptance gate | `synthetic_container` mapping | `private_final` mapping |
| --- | --- | --- |
| `fresh_container_functional_smoke` | `pass` only when `overall_status=pass`; `fail` when `overall_status=fail`; otherwise `blocked`. | `blocked` with reason `private_final_smoke_is_not_container_proof` unless separate container proof evidence is explicitly provided in a later slice. |
| `private_final_live_smoke_redacted` | `blocked` with reason `synthetic_evidence_cannot_prove_private_final_smoke`; never `pass`. | mirrors `overall_status`: `pass`/`fail`/`blocked`, using only redacted labels/counts/hashes. |
| `private_leakage_scan` | mirrors `meta_leakage_scan` check status for synthetic public fixtures, but notes `synthetic_only`. | mirrors `meta_leakage_scan` check status and material-manifest content-safety status. |
| `compile_export` | `pass` only when `exported_pdf_tex_evidence=pass`; `fail` on contradiction/unsafe evidence; otherwise `blocked`. | same as synthetic. |
| `exported_pdf_tex_evidence_bundle` | mirrors `exported_pdf_tex_evidence`. | mirrors `exported_pdf_tex_evidence`. |

Tests must prove `build_acceptance_ledger(fresh_smoke_acceptance_evidence(summary))`
accepts the mapping and that synthetic-only evidence can never mark
`private_final_live_smoke_redacted` as `pass`.

## 5. Public-safety contract

The public summary and acceptance evidence must not include:

- raw evidence root path;
- raw material root path;
- private zip names;
- raw material filenames, captions, claims, source snippets, BibTeX keys, figure
  names, or paper-specific domain identifiers;
- absolute paths;
- secrets or private markers;
- raw `omx ...`, `codex ...`, provider command prompts, or raw LLM messages.

Allowed:

- redacted labels derived from path/content hashes;
- counts;
- status codes;
- allowed smoke verdict alphabet;
- relative public artifact names like `readable/verdict.json` or
  `artifacts/fresh-smoke-acceptance-summary.json`.

Unsafe input should fail closed and the returned public payload must not reproduce
unsafe values.

Material-manifest safety:

- `material_manifest` is optional for `synthetic_container` and required for a
  `private_final` pass.
- If present, the summarizer may read only structural metadata such as counts,
  schema version, byte counts, and hashes.
- Any manifest value that looks like a raw private filename, private marker,
  absolute path, source snippet, prompt, BibTeX key, figure name, or domain
  identifier must fail closed with a generic code such as
  `material_manifest_public_payload_unsafe`.
- The unsafe value itself must never appear in summary JSON, CLI output, MCP
  output, acceptance evidence, notes, or reasons.

Verdict/readiness wording safety:

- `FORBIDDEN_SMOKE_VERDICTS` applies to the top-level `smoke_verdict` field.
- Nested fields such as `qa_loop_terminal_verdict` may contain machine states
  like `human_needed` when already permitted by `validate_fresh_smoke_verdict`,
  but the AG public summary must render them as bounded process states rather
  than manuscript-success claims.
- The summary must never expose or imply `submission_ready`, `camera_ready`, or
  final author readiness. AG can say only that the smoke loop predicates passed,
  blocked, or failed.

## 6. Tests to add first

Minimum failing tests before implementation:

1. `tests/test_fresh_smoke_acceptance.py`
   - synthetic complete evidence root with allowed `pass_loop_verified` verdict
     produces summary `overall_status=pass` and acceptance evidence consumable by
     `build_acceptance_ledger`;
   - missing verdict/evidence files produce `blocked`, not pass;
   - forbidden verdict states such as `submission_ready` and
     `ready_for_human_finalization` produce `fail` and are not treated as success;
   - meta leakage nonzero matches produces `fail`;
   - material invariance fail produces `fail`;
   - artifact manifest missing PDF/TeX produces `blocked`;
   - `operator_feedback_cycles_attempted=5` is accepted when split counters
     sum correctly;
   - `operator_feedback_cycles_attempted=6` fails closed;
   - raw private-looking evidence root/material manifest path is redacted in JSON;
   - unsafe private marker in a public evidence artifact fails closed without
     reproducing the marker.
   - unsafe private marker or raw private-looking filename inside
     `material_manifest` fails closed without reproducing the unsafe string.
   - synthetic mode never marks `private_final_live_smoke_redacted` as `pass`;
   - private mode cannot pass without a safe material manifest.
2. CLI tests:
   - `summarize-fresh-smoke --evidence-root synthetic --json` returns schema and
     redacted labels;
   - `--output` writes a summary while not echoing raw absolute output path.
3. MCP tests:
   - `summarize_fresh_smoke` appears in `TOOLS`/`TOOL_HANDLERS`;
   - handler returns public-safe schema and does not echo raw paths.
4. Existing tests remain green:
   - `tests/test_private_smoke_safety.py`
   - `tests/test_fresh_smoke_inputs.py`
   - `tests/test_orchestra_acceptance_ledger.py`
   - `tests/test_orchestrator_cli_entrypoints.py`
   - `tests/test_orchestrator_mcp_entrypoints.py`

## 7. Validation before implementation commit

Local:

```bash
.venv/bin/python -m pytest tests/test_fresh_smoke_acceptance.py \
  tests/test_private_smoke_safety.py \
  tests/test_fresh_smoke_inputs.py \
  tests/test_orchestra_acceptance_ledger.py \
  tests/test_orchestrator_cli_entrypoints.py \
  tests/test_orchestrator_mcp_entrypoints.py -q
.venv/bin/python -m pytest -q
scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
grep -RIn "<private-domain literal>" $(git ls-files 'docs/**' 'paperorchestra/**' 'tests/**' 'skills/**' 'README.md' 'ENVIRONMENT.md') 2>/dev/null | head -50 || true
git diff --check
```

Critic implementation validation is required before commit/push.

## 8. Container proof after push

After implementation commit is pushed:

```bash
docker run --rm \
  -v /tmp/paperorchestra-private-denylist.txt:/tmp/paperorchestra-private-denylist.txt:ro \
  paperorchestra-ubuntu-tools:24.04 bash -lc 'set -euo pipefail
WORK=/tmp/paperorchestra-ag-proof
rm -rf "$WORK"
git clone --branch orchestrator-v1-runtime https://github.com/kosh7707/paperorchestra-for-codex.git "$WORK" >/tmp/git-clone.log
cd "$WORK"
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]" >/tmp/pip-install.log
python -m pytest tests/test_fresh_smoke_acceptance.py tests/test_private_smoke_safety.py tests/test_fresh_smoke_inputs.py tests/test_orchestra_acceptance_ledger.py -q
scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
printf "HEAD=%s\n" "$(git rev-parse --short HEAD)"
'
```

Record proof in this plan or a follow-up evidence commit.

## 9. Private final live smoke handoff

After AG implementation and container proof, the actual private final live smoke
must run outside the public repo with private material already prepared outside
tracked files. Public commit evidence may record only:

- redacted evidence root label;
- material manifest hash/counts;
- final summary status and failing predicate codes;
- operator/human_needed cycle counts;
- artifact counts and SHA-256 hashes;
- leakage scan pass/fail;
- no raw material names, domains, claims, figures, or references.

The private run command shape remains:

```bash
scripts/fresh-full-live-smoke-loop.sh \
  --evidence-root <outside-repo-evidence-dir> \
  --material-root <outside-repo-private-material-dir> \
  --expected-material-root <outside-repo-private-material-dir> \
  --max-operator-cycles 5
```

A public redacted summary may be produced with:

```bash
paperorchestra summarize-fresh-smoke \
  --evidence-root <outside-repo-evidence-dir> \
  --material-manifest <outside-repo-private-material-dir>/private-smoke-manifest.redacted.json \
  --output <repo-or-outside-redacted-summary-path> \
  --json
```

If the private smoke fails, the public summary should record `fail` or `blocked`
with generic failing codes rather than pretending success.

## 10. Stop/replan triggers

Stop and replan if:

- summarizer must read or emit raw private material to decide status;
- forbidden raw verdicts can pass;
- output leaks private paths/names/claims/figures/references;
- acceptance evidence cannot be consumed by `build_acceptance_ledger` without
  weakening ledger safety;
- implementation tries to run the long smoke loop, Docker, OMX, Codex, web, or
  live models inside unit tests/product summarizer;
- public tests require private material.

## 11. Slice AG implementation evidence

Plan validation:

- Initial Critic verdict: `CHANGES_REQUIRED`.
- Plan revisions added explicit `smoke_mode`, exact acceptance-ledger status
  mapping, max-five operator-cycle semantics, top-level verdict/readiness wording
  safety, and material-manifest content safety.
- Final Critic plan verdict: `APPROVE`.
- Plan commit: `e320d35 Define redacted final-smoke acceptance before implementation`.

Implementation:

- Added `paperorchestra/fresh_smoke_acceptance.py`.
- Added CLI: `paperorchestra summarize-fresh-smoke`.
- Added MCP tool: `summarize_fresh_smoke`.
- Added public synthetic tests in `tests/test_fresh_smoke_acceptance.py`.
- Implementation commit: `d0ca29d Summarize fresh smoke evidence without leaking private material`.

Test-first evidence:

```bash
.venv/bin/python -m pytest tests/test_fresh_smoke_acceptance.py -q
# before implementation: ModuleNotFoundError: paperorchestra.fresh_smoke_acceptance
```

Local verification after implementation:

```bash
.venv/bin/python -m pytest tests/test_fresh_smoke_acceptance.py -q
# 10 passed

.venv/bin/python -m pytest tests/test_fresh_smoke_acceptance.py \
  tests/test_private_smoke_safety.py \
  tests/test_fresh_smoke_inputs.py \
  tests/test_orchestra_acceptance_ledger.py \
  tests/test_orchestrator_cli_entrypoints.py \
  tests/test_orchestrator_mcp_entrypoints.py -q
# 68 passed, 20 subtests passed

.venv/bin/python -m pytest -q
# 977 passed, 182 subtests passed

scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
# status ok, match_count 0

grep -RIn "<private-domain literal>" $(git ls-files 'docs/**' 'paperorchestra/**' 'tests/**' 'skills/**' 'README.md' 'ENVIRONMENT.md') 2>/dev/null | head -50 || true
# no output

git diff --check
# clean
```

Implementation Critic validation:

- Initial implementation verdict: `CHANGES_REQUIRED`.
- Required fixes:
  - private-final leakage mapping must combine meta-leakage and manifest safety;
  - MCP relative paths must resolve against client-supplied `cwd`;
  - negative operator cycle counters should fail closed.
- Added regressions for all three.
- Final implementation verdict: `APPROVE`.

Container proof after push:

```bash
docker run --rm \
  -v /tmp/paperorchestra-private-denylist.txt:/tmp/paperorchestra-private-denylist.txt:ro \
  paperorchestra-ubuntu-tools:24.04 bash -lc '...'
# 68 passed, 20 subtests passed
# leakage scan status ok, match_count 0
# private-domain literal grep no output
# HEAD=d0ca29d
```
