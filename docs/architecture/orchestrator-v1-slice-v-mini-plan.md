# Slice V mini-plan — apply local execution outcomes to returned state

Status: implemented; Critic-approved after malformed source-digest/no-evidence coverage; full-suite and leakage scan passed
Date: 2026-05-13
Branch: `orchestrator-v1-runtime`

## 1. Target result

Slice U exposed one-step local execution through CLI/MCP, but the returned state can still show the pre-execution action as the next action. Example: `build_claim_graph` executes successfully while returned facets still say `claims=missing` and next action remains `build_claim_graph`.

Slice V adds a small orchestrator-owned post-execution transition layer for local execution records. Executors still cannot mutate `OrchestraState`; the orchestrator applies public-safe execution evidence after the mutation guard.

```text
executor.execute(action, state)  # no state mutation allowed
-> ExecutionRecord(evidence_refs=[claim_graph...])
-> orchestrator appends execution evidence
-> orchestrator applies recognized local outcome to returned state
-> ActionPlanner replans next action
```

## 2. Scope

Add/extend:

```text
paperorchestra/orchestrator.py
tests/test_orchestrator_action_executor.py
tests/test_orchestrator_cli_entrypoints.py
tests/test_orchestrator_mcp_entrypoints.py
docs/architecture/orchestrator-v1-slice-v-mini-plan.md
```

No live adapters, no CLI/MCP default behavior changes.

## 3. Public contract

Implementation shape:

```python
_apply_local_execution_record(state: OrchestraState, record_public: dict[str, object]) -> None
```

or an equivalent small internal helper. This keeps hard-to-reach transitions
unit-testable without unnatural CLI setup.

For recognized `executed_local` records:

- `build_claim_graph` with ready public claim graph evidence:
  - `facets.claims = candidate`;
  - `facets.evidence = research_needed` when high-critical evidence obligations require research;
  - `facets.citations = unknown_refs` when critical citation obligations are unknown;
  - `blocking_reasons` includes report blockers without duplicates;
  - `readiness`/five-axis status refresh;
  - next action replans, normally to `$autoresearch` for machine-solvable evidence work.

- `build_source_digest` with sufficient digest:
  - `facets.material = inventoried_sufficient`;
  - `facets.source_digest = ready`;
  - `facets.artifacts = fresh`;
  - next action replans.

- `inspect_material` may record inventory but should not claim source digest readiness by itself.

Blocked, unsupported, fake, and unknown adapter records do not advance readiness/facets.

## 4. Required behavior

- executor mutation guard remains before transition application;
- post-execution transitions use only public `ExecutionRecord.to_public_dict()` / evidence payloads;
- no raw text/path/private fields are required;
- if public evidence is absent or malformed, do not advance state;
- claim graph transition requires:
  - `schema_version=claim-graph/1`;
  - `ready=true`;
  - expected list fields for evidence/citation obligations;
  - `private_safe_summary=true`.
- source digest transition requires:
  - `schema_version=source-digest/1`;
  - `sufficient=true`;
  - `private_safe_summary=true`.
- fake execution still does not advance facets/readiness;
- local claim graph execution must not mark drafting allowed or ready-for-finalization;
- CLI/MCP opt-in should now show the post-action next action rather than repeating the completed local action;
- public payload/evidence must remain private-safe.

## 5. Tests to add first

1. direct orchestrator local `build_claim_graph` step advances returned facets from `claims=missing` to `claims=candidate`;
2. returned readiness becomes `research_needed`, not ready/drafting;
3. returned next action becomes `start_autoresearch` with `$autoresearch`, not `build_claim_graph`;
4. fake executor still does not advance facets/readiness;
5. malformed/no-evidence local record does not advance facets;
6. direct transition helper test: local `build_source_digest` record with public sufficient source digest sets `material=inventoried_sufficient`, `source_digest=ready`, `artifacts=fresh`, and replans to `build_claim_graph`;
7. direct transition helper test: local `inspect_material` inventory evidence does not set `source_digest=ready` and does not jump to `build_claim_graph`;
8. malformed claim graph/source digest evidence missing schema/private-safe flags does not advance facets;
9. CLI `orchestrate --execute-local --json` returns post-action next action `start_autoresearch`;
10. MCP `execute_local=true` returns post-action next action `start_autoresearch`;
11. no `paper_full_tex`, raw claim text, material path, `omx `, or `codex ` leaks.

## 6. Validation for this slice

Required before commit/push:

```bash
.venv/bin/python -m pytest tests/test_orchestrator_action_executor.py tests/test_orchestrator_cli_entrypoints.py tests/test_orchestrator_mcp_entrypoints.py -q
git diff --check
```

Preferred:

```bash
.venv/bin/python -m pytest -q
scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
```

Container proof after push when practical:

```bash
docker run --rm paperorchestra-ubuntu-tools:24.04 bash -lc '
  git clone https://github.com/kosh7707/paperorchestra-for-codex.git repo &&
  cd repo && git checkout orchestrator-v1-runtime &&
  python3 -m venv .venv && . .venv/bin/activate &&
  python -m pip install -e ".[dev]" &&
  python -m pytest tests/test_orchestrator_action_executor.py tests/test_orchestrator_cli_entrypoints.py tests/test_orchestrator_mcp_entrypoints.py -q
'
```

Critic plan validation is required before implementation. Critic implementation validation is required before commit.

Current evidence:

- Critic plan validation: CHANGES_REQUIRED until hard-to-reach
  source-digest/inspect-material transitions and strict evidence validation were
  testable through a helper; revised plan APPROVE.
- Critic implementation validation: CHANGES_REQUIRED until malformed
  source-digest and no-evidence local records had direct negative coverage;
  re-validation APPROVE.
- Targeted tests:
  - `.venv/bin/python -m pytest tests/test_orchestrator_action_executor.py tests/test_orchestrator_cli_entrypoints.py tests/test_orchestrator_mcp_entrypoints.py -q`
    → `52 passed, 14 subtests passed`
- Final full suite: `.venv/bin/python -m pytest -q`
  → `856 passed, 127 subtests passed`
- Private leakage scan:
  `scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json`
  → `status=ok`, `scanned_file_count=202`, `match_count=0`
- Fresh container targeted proof after push:
  `docker run --rm paperorchestra-ubuntu-tools:24.04 ... git checkout orchestrator-v1-runtime ... python -m pytest tests/test_orchestrator_action_executor.py tests/test_orchestrator_cli_entrypoints.py tests/test_orchestrator_mcp_entrypoints.py -q`
  → checkout `3ff94ae`, `52 passed, 14 subtests passed`

## 7. Explicit non-goals

Slice V must not:

- let executors mutate state directly;
- execute live search/model/OMX/compile/export/drafting;
- fully replace `_run_until_blocked`;
- build research missions or invoke OMX;
- mark local evidence generation as final readiness;
- require private material fixtures.

## 8. Stop/replan triggers

Stop and replan if:

- transition logic needs raw private text;
- local execution starts to duplicate full pipeline behavior;
- next actions regress to human_needed for machine-solvable evidence gaps;
- fake/unsupported records advance state;
- CLI/MCP default behavior changes.
