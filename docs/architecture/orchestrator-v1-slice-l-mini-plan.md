# Slice L mini-plan — public-safe orchestrator evidence bundle persistence

Status: implemented and Critic-approved
Date: 2026-05-13
Branch: `orchestrator-v1-runtime`

## 1. Target result

Persist the in-memory `OrchestraState.evidence_refs` surface as a reproducible public-safe evidence bundle:

```text
run_until_blocked state
-> orchestra-state.json
-> evidence/*.json
-> manifest.json with hashes and paths
-> CLI `orchestrate --write-evidence` reports the bundle
```

This slice makes the current orchestrator skeleton auditable in fresh/container/private smoke runs without requiring a live model or OMX execution.

## 2. Why this slice exists

Slices G-K add useful state/evidence refs, but they currently live primarily in CLI/MCP JSON output. Long-running QA needs stable files that can be inspected, copied, hashed, and attached to reports.

The bundle should answer:

- which state was inspected;
- which evidence refs were produced;
- where each evidence payload was written;
- which hashes prove the files did not silently change;
- whether public-safe redaction was applied.

## 3. Public module and integration points

Proposed file:

```text
paperorchestra/orchestra_evidence.py
```

Types/functions:

```text
write_orchestrator_evidence_bundle(cwd, state, output_dir=None)
```

Integrate with:

```text
paperorchestra/cli.py
```

Add CLI option:

```bash
paperorchestra orchestrate --material <path> --write-evidence [--evidence-output <dir>] --json
```

Default output location should stay inside the project workspace:

```text
.paper-orchestra/orchestrator-evidence/
```

User-provided `--evidence-output` is resolved and must remain under the current workspace for this slice. Absolute paths or traversal outside `cwd` are rejected. A future explicit opt-in flag may relax this, but Slice L must default to workspace-contained evidence.

## 4. Public-safe policy

The writer must use `state.to_public_dict()` and must defensively, recursively redact private-looking keys in nested evidence payloads:

- keys starting `private_`;
- `raw_text`, `prompt`, `argv`, `executable_command`;
- any explicit private notes from state.

It should never write raw private material by default. It may write hashes, counts, redacted labels, and relative file names.

## 5. Manifest policy

Manifest should include:

- schema version;
- state file path/hash;
- evidence file entries with kind, index, file path/hash;
- evidence count;
- private_safe_summary=true.

Manifest file entries should use paths relative to the bundle root, not absolute workspace/private paths. The CLI may return the resolved manifest path for convenience, but the manifest content itself must be portable/public-safe.

It must not use manifest success as manuscript readiness. This is evidence persistence only.

## 6. Tests to add first

Proposed file:

```text
tests/test_orchestra_evidence_bundle.py
```

Minimum tests:

1. writes state, evidence files, and manifest with stable hashes;
2. state file omits private notes / redacts author override via `to_public_dict`;
3. evidence payload redacts raw private marker keys defensively;
4. nested evidence payload redaction removes `raw_text`, `private_*`, `prompt`, `argv`, and `executable_command` at any depth;
5. user-provided `--evidence-output` outside the workspace is rejected;
6. manifest JSON stores relative paths and does not contain the absolute temp/workspace path;
7. CLI `orchestrate --write-evidence --json` writes a bundle and reports manifest path;
8. bundle writing does not mark drafting allowed or readiness pass.

## 7. Validation for this slice

Required before commit/push:

```bash
.venv/bin/python -m pytest tests/test_orchestra_evidence_bundle.py tests/test_orchestrator_cli_entrypoints.py -q
.venv/bin/python -m pytest tests/test_orchestra_references.py tests/test_orchestra_omx_invocation.py tests/test_orchestra_research_mission.py -q
.venv/bin/python -m pytest tests/test_orchestra_*.py tests/test_private_smoke_safety.py -q
git diff --check
```

Preferred:

```bash
.venv/bin/python -m pytest -q
scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
```

Critic plan validation is required before implementation. Critic implementation validation is required before commit.

Completed validation evidence:

```bash
.venv/bin/python -m pytest tests/test_orchestra_evidence_bundle.py tests/test_orchestrator_cli_entrypoints.py -q
# 8 passed

.venv/bin/python -m pytest tests/test_orchestra_references.py tests/test_orchestra_omx_invocation.py tests/test_orchestra_research_mission.py -q
# 19 passed, 8 subtests passed

.venv/bin/python -m pytest tests/test_orchestra_*.py tests/test_private_smoke_safety.py -q
# 91 passed, 8 subtests passed

.venv/bin/python -m pytest -q
# 789 passed, 113 subtests passed

scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
# status ok, scanned_file_count=185, match_count=0

git diff --check
# clean
```

Critic implementation validation: APPROVE after fixing bundle-wide workspace path redaction and preserving
`private_safe` / `private_safe_summary` booleans.

## 8. Explicit non-goals

Slice L must not:

- execute research, OMX, web, or model calls;
- mark evidence refs as validated merely because they are persisted;
- write private/raw material by default;
- change manuscript generation behavior;
- replace existing session artifact export commands.

## 9. Stop/replan triggers

Stop and replan if:

- raw private markers appear in written bundle files;
- manifest status is treated as readiness/pass;
- evidence bundle output escapes the workspace by default;
- manifest content records absolute private/workspace paths;
- nested payload redaction misses raw/private keys;
- tests require live providers or private material.
