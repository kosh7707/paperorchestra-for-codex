# Slice AF mini-plan — score, Critic consensus, and verifier evidence harness

Status: draft mini-plan requiring Critic validation before tests or implementation
Date: 2026-05-14
Branch: `orchestrator-v1-runtime`
Scope: public, domain-general score/consensus/verifier evidence contracts. Do not include private smoke material, private-domain terms, or private material names.

## 0. Pre-plan issue check

Required by the post-Z workflow plan before every slice mini-plan:

```bash
gh issue list --state open --json number,title,labels,updatedAt,url --limit 50
# []
```

No actionable open GitHub issue blocked Slice AF planning.

## 1. Target result

Slice AF closes the gap between “we have score/consensus scaffolding” and “a
Verifier can prove the score/consensus evidence is complete enough to trust a
full-loop readiness decision.” It does not run live LLM critics. It provides a
public-safe, deterministic verifier checklist that future live Critic/Ralph work
can cite.

AF target from the post-Z plan:

- deterministic scoring bundle builders per phase;
- fake Critic outputs with evidence-linked rationales;
- two-Critic consensus schema and disagreement/adjudication path;
- Verifier evidence checklist;
- hard-gate override tests.

Existing code already covers most of the first three bullets. AF should preserve
and strengthen those surfaces while adding the missing verifier/checklist bridge.

## 2. Current baseline

Existing surfaces:

- `paperorchestra/orchestra_scoring.py`
  - `ScoringBundleBuilder`, `ScoringInputBundle`, `ScholarlyScore`,
    `ScoreDimensionAssessment`, compact scorecard renderer;
  - already rejects missing dimensions, no evidence links, invalid scores,
    rejected `reviewer_attack_surface`, unknown dimensions, and private details.
- `paperorchestra/orchestra_consensus.py`
  - `CriticVerdict`, `ConsensusPolicy`, `CriticConsensus`;
  - already requires two critics, evidence links, and routes disagreement to
    `run_third_critic_adjudication`.
- `paperorchestra/orchestra_loop.py`
  - hard-gate failures override high scores;
  - high-risk readiness routes to Critic consensus;
  - consensus disagreement routes to adjudication;
  - compile/export only after gates, score bundle, score, consensus, and figure
    checks allow.
- `paperorchestra/orchestra_acceptance.py`
  - acceptance gate list includes
    `critic_consensus_near_ready_or_better` and
    `verifier_evidence_completeness_no_leakage`;
  - evidence refs are public-safe validated.

Gaps:

- no single Verifier checklist artifact states whether score bundle, score,
  consensus, hard gates, compile/export evidence, and public-safety evidence are
  complete;
- no function converts verifier checklist status into acceptance-ledger evidence
  for `verifier_evidence_completeness_no_leakage`;
- no CLI/MCP-accessible diagnostic for the verifier checklist;
- tests do not yet prove that a high score + missing verifier evidence remains
  incomplete;
- tests do not yet prove that private strings/paths in verifier inputs are
  rejected or redacted.

## 3. Implementation boundary

Add one small deterministic module rather than changing live critic execution:

```text
paperorchestra/orchestra_verifier.py
  VERIFIER_CHECKLIST_SCHEMA_VERSION = "verifier-evidence-checklist/1"
  VerifierChecklistItem
  VerifierEvidenceChecklist
  build_verifier_evidence_checklist(...)
  verifier_acceptance_evidence(checklist)
  write_verifier_evidence_checklist(cwd, *, output_path=None, ...)
```

The builder should accept already-built objects and optional artifact refs:

```python
build_verifier_evidence_checklist(
    state: OrchestraState,
    scoring_bundle: ScoringInputBundle | None,
    score: ScholarlyScore | None,
    consensus: CriticConsensus | None,
    *,
    compiled: bool = False,
    exported: bool = False,
    artifact_refs: Mapping[str, str] | None = None,
) -> VerifierEvidenceChecklist
```

CLI addition:

```bash
paperorchestra verify-evidence-checklist [--output path] [--json]
```

MCP addition:

```text
verify_evidence_checklist(cwd?, output?)
```

For the CLI/MCP diagnostic with only a session on disk, it is acceptable to emit a
mostly `blocked` checklist when scoring/consensus objects are not present. That
makes incompleteness explicit instead of fabricating a pass.

## 4. Public schema contract

Verifier checklist output:

```json
{
  "schema_version": "verifier-evidence-checklist/1",
  "overall_status": "pass | blocked | fail",
  "items": [
    {
      "id": "scoring_bundle_complete",
      "status": "pass | blocked | fail",
      "evidence_refs": [{"kind": "score_bundle", "path": "artifacts/...", "sha256": "..."}],
      "reason": "...",
      "private_safe": true
    }
  ],
  "acceptance_evidence": {
    "status": "pass | blocked | fail",
    "evidence_refs": [...],
    "notes": [...]
  },
  "private_safe_summary": true
}
```

Required item IDs:

1. `scoring_bundle_complete`
2. `score_valid_and_evidence_linked`
3. `critic_consensus_two_or_more`
4. `critic_consensus_near_ready_or_better`
5. `hard_gates_no_fail`
6. `compile_export_accounted_for`
7. `public_safety_no_raw_private_evidence`

Rules:

- `overall_status=pass` only when every required item passes.
- `blocked` is used for missing/incomplete evidence that can be produced later.
- `fail` is used for explicit unsafe/private evidence or hard-gate failure.
- A high score must not override a failed hard gate or missing verifier item.
- Acceptance evidence for `verifier_evidence_completeness_no_leakage` is `pass`
  only when the checklist passes.
- Public output must not include raw private strings, absolute paths, raw prompts,
  manuscript text, or raw command strings.

## 5. Integration points

Required:

1. New `paperorchestra/orchestra_verifier.py` with public-safe dataclasses.
2. CLI `verify-evidence-checklist` in `paperorchestra/cli.py`.
3. MCP `verify_evidence_checklist` in `paperorchestra/mcp_server.py`.
4. `orchestra_acceptance.py` remains the final acceptance-ledger validator; AF
   adds a producer for the verifier gate evidence.
5. Existing score/consensus/loop behavior must remain green.

Non-goals:

- Do not spawn live Critic subagents from product code.
- Do not call OMX/Codex/LLM/web from the verifier.
- Do not mark the entire thread goal complete.
- Do not use private material in public tests.
- Do not alter citation or figure gates beyond consuming their status as evidence
  refs in future slices.

## 6. Tests to add first

Minimum failing tests before implementation:

1. `tests/test_orchestra_verifier.py`
   - complete score bundle + valid score + two agreeing near-ready critics + pass
     hard gates + compile/export accounted -> checklist pass;
   - missing scoring bundle blocks verifier even when score is high;
   - invalid score blocks verifier;
   - one critic blocks `critic_consensus_two_or_more`;
   - two disagreeing critics block and expose adjudication action, not pass;
   - hard-gate failure produces `fail` despite high score and near-ready critics;
   - private marker / absolute path in artifact refs is rejected or redacted;
   - acceptance evidence maps to `verifier_evidence_completeness_no_leakage` and
     can be consumed by `build_acceptance_ledger`.
2. CLI tests:
   - `verify-evidence-checklist --json` returns schema and blocked status when no
     score/consensus evidence is present;
   - `--output` writes artifact under the current session artifact dir or explicit
     path.
3. MCP tests:
   - `verify_evidence_checklist` appears in `TOOLS` and `TOOL_HANDLERS`;
   - handler returns schema and public-safe payload.
4. Existing tests remain green:
   - `tests/test_orchestra_scoring.py`
   - `tests/test_orchestra_consensus.py`
   - `tests/test_orchestra_full_loop_planner.py`
   - `tests/test_orchestra_acceptance_ledger.py`
   - `tests/test_orchestrator_cli_entrypoints.py`
   - `tests/test_orchestrator_mcp_entrypoints.py`

## 7. Validation before implementation commit

Local:

```bash
.venv/bin/python -m pytest tests/test_orchestra_verifier.py \
  tests/test_orchestra_scoring.py \
  tests/test_orchestra_consensus.py \
  tests/test_orchestra_full_loop_planner.py \
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
WORK=/tmp/paperorchestra-af-proof
rm -rf "$WORK"
git clone --branch orchestrator-v1-runtime https://github.com/kosh7707/paperorchestra-for-codex.git "$WORK" >/tmp/git-clone.log
cd "$WORK"
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]" >/tmp/pip-install.log
python -m pytest tests/test_orchestra_verifier.py tests/test_orchestra_scoring.py tests/test_orchestra_consensus.py tests/test_orchestra_full_loop_planner.py tests/test_orchestra_acceptance_ledger.py -q
scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
printf "HEAD=%s\n" "$(git rev-parse --short HEAD)"
'
```

Record proof in this plan or a follow-up evidence commit.

## 9. Stop/replan triggers

Stop and replan if:

- verifier output can pass with missing score/consensus/hard-gate evidence;
- high score or Critic consensus can override a hard-gate fail;
- public verifier output leaks private material, absolute paths, raw prompts, or
  command strings;
- product code tries to spawn live Critic/OMX/LLM work in this slice;
- acceptance evidence cannot be consumed by `build_acceptance_ledger` without
  weakening its public-safety validator;
- tests require private material or live services.

## 10. Critic-required contract clarifications

The following clarifications are binding for AF implementation.

### 10.1 Exact checklist item status rules

All checklist items are required. Overall status is:

- `fail` if any item is `fail`;
- else `blocked` if any item is `blocked`;
- else `pass`.

Item rules:

1. `scoring_bundle_complete`
   - `pass`: `scoring_bundle` exists, schema is `scholarly-score-input-bundle/1`,
     `complete=true`, manuscript hash is 64 hex chars, required artifacts are
     non-empty public refs, and `private_safe=true` in public payload.
   - `blocked`: scoring bundle is missing or incomplete because required evidence
     has not been produced yet.
   - `fail`: scoring bundle public payload is unsafe or malformed beyond normal
     missing-evidence blockers.
2. `score_valid_and_evidence_linked`
   - `pass`: `score` exists, `score.valid=true`, every required dimension exists,
     every dimension has evidence links, and public payload is private-safe.
   - `blocked`: score is missing, has missing dimensions, missing evidence links,
     or other repairable validation blockers.
   - `fail`: score contains unsafe public evidence refs, rejected dimensions,
     out-of-range scores, invalid confidence, or malformed public payload.
3. `critic_consensus_two_or_more`
   - `pass`: consensus exists and includes at least two valid verdicts with
     evidence links.
   - `blocked`: consensus is missing or has fewer than two verdicts.
   - `fail`: any verdict lacks evidence links or consensus public payload is unsafe.
4. `critic_consensus_near_ready_or_better`
   - Accepted readiness bands: `near_ready`, `human_finalization_candidate`,
     `ready_for_human_finalization`, and `ready`.
   - `pass`: consensus status is `pass` and readiness band is accepted.
   - `blocked`: consensus needs adjudication or readiness band is below accepted
     threshold.
   - `fail`: consensus status is `failed` or public payload is unsafe.
5. `hard_gates_no_fail`
   - `pass`: `state.hard_gates.status == "pass"`.
   - `blocked`: hard gates are `unknown`/not yet evaluated.
   - `fail`: hard gates status is `fail`.
6. `compile_export_accounted_for`
   - `pass`: `compiled=true` and `exported=true`.
   - `blocked`: compile/export is not reached yet, missing, or only partially
     complete. This is not a failure unless unsafe evidence is supplied.
   - `fail`: compile/export evidence refs are unsafe or contradictory.
7. `public_safety_no_raw_private_evidence`
   - `pass`: all public payloads and artifact refs pass bounded public-safety
     validation.
   - `blocked`: not used for ordinary missing evidence.
   - `fail`: any public artifact ref, note, or payload contains a private marker,
     absolute path, raw `omx ...` command, raw prompt/raw_text/executable command
     key, or raw manuscript text marker.

### 10.2 Default path and output containment

Default artifact path:

```text
verifier_evidence_checklist_path(cwd) -> artifact_path(cwd, "verifier_evidence_checklist.json")
```

`write_verifier_evidence_checklist` may write to:

- the default session artifact path; or
- an explicit `output_path` supplied by CLI/operator.

The public payload must never embed raw absolute output paths. It may include a
redacted output label or workspace-relative artifact path only. MCP `output` is a
diagnostic file-write request, not an arbitrary execution primitive; tests must
cover that returned payload does not leak the raw output path.

### 10.3 Acceptance evidence shape

`verifier_acceptance_evidence(checklist)` returns a full mapping directly
consumable by `build_acceptance_ledger`:

```python
{
    "verifier_evidence_completeness_no_leakage": {
        "status": "pass | blocked | fail",
        "evidence_refs": [
            {
                "kind": "verifier/checklist",
                "summary": "verifier checklist pass|blocked|fail",
                "path": "artifacts/verifier_evidence_checklist.json",
                "sha256": "... optional 64 hex ..."
            }
        ],
        "notes": ["public-safe verifier evidence checklist"]
    }
}
```

Tests must prove this mapping can be passed directly to
`build_acceptance_ledger(...)` and produces the expected gate status without
adapter logic.

### 10.4 Synthetic Critic evidence wording

AF tests may construct deterministic `CriticVerdict` / `CriticConsensus` objects.
The verifier must describe these as a provided consensus object or verifier input.
It must not claim that live Critic, OMX, Ralph, or Codex subagents actually ran.
Live Critic consensus remains future runtime evidence, not an AF product-code
side effect.

### 10.5 Artifact-ref public-safety behavior

Verifier artifact refs are fail-closed. The implementation should reject/fail on:

- private markers such as `PRIVATE`, `SECRET`, or `TOKEN`;
- absolute paths;
- raw `omx ...` command text;
- keys named `prompt`, `raw_text`, `argv`, or `executable_command` anywhere in a
  supplied mapping;
- raw manuscript/source text markers.

Allowed refs are bounded strings such as relative artifact paths, 64-hex hashes,
redacted labels, and low-cardinality reason codes.

Additional tests required by this clarification:

- unsafe artifact ref containing a raw `omx ...` command causes checklist fail;
- unsafe artifact ref containing an absolute path causes checklist fail;
- unsafe artifact ref containing `PRIVATE` causes checklist fail;
- unsafe artifact ref containing a forbidden `prompt` or `raw_text` key causes
  checklist fail;
- public payload for any unsafe case must not reproduce the unsafe value.
