# Slice P mini-plan — user-facing scorecard summary in state/CLI/MCP

Status: implemented and Critic-approved
Date: 2026-05-13
Branch: `orchestrator-v1-runtime`

## 1. Target result

Slice O defined the full 11-dimension scholarly scorecard contract, but current first-user surfaces still mostly show only:

```text
Readiness: ...
Next action: ...
```

Slice P adds a public-safe compact scorecard summary to the orchestrator state and high-level CLI/MCP outputs:

```text
OrchestraState.to_public_dict()
-> scorecard_summary
-> CLI inspect-state/orchestrate human summary
-> MCP inspect_state/orchestrate JSON payloads
```

This is a display/routing surface only. It does not compute manuscript quality from heuristics and does not let scores override hard gates.

## 2. Scope

Add/extend:

```text
paperorchestra/orchestra_scorecard.py
paperorchestra/orchestra_state.py
paperorchestra/cli.py
tests/test_orchestra_scorecard_summary.py
tests/test_orchestrator_cli_entrypoints.py
tests/test_orchestrator_mcp_entrypoints.py
docs/architecture/orchestrator-v1-slice-p-mini-plan.md
```

## 3. Required behavior

- `scorecard_summary` must be derived from `OrchestraState.scores` / hard gates / readiness, not from model calls or text heuristics;
- unscored states must render as `unscored` and must not imply quality approval;
- scored states should expose:
  - overall score;
  - readiness band;
  - weakest known accepted dimensions;
  - hard-gate blockers;
  - current readiness label/status;
  - private_safe=true;
- unknown/domain-specific score dimensions from `ScoreSummary.dimensions` must not appear in public summary;
- hard-gate failures must dominate the scorecard status even when overall score is high;
- CLI non-JSON summaries should include a compact score line and weakest dimensions if available;
- JSON/MCP output should include machine-readable `scorecard_summary` inside state payloads.

## 4. Tests to add first

Add/update tests before implementation:

1. unscored state returns `scorecard_summary.status=unscored`;
2. scored state lists weakest accepted dimensions in ascending score order;
3. unknown/domain-specific dimension is omitted from public summary;
4. hard-gate failure marks scorecard status as `blocked_by_hard_gate` despite high score;
5. `OrchestraState.to_public_dict()` includes `scorecard_summary`;
6. CLI `inspect-state` non-JSON output includes score/readiness/next-action lines;
7. CLI summary does not print unknown private dimension labels;
8. MCP `inspect_state` payload includes `scorecard_summary`;
9. existing JSON state contract and scorecard tests still pass.

## 5. Validation for this slice

Required before commit/push:

```bash
.venv/bin/python -m pytest tests/test_orchestra_scorecard_summary.py tests/test_orchestra_state_contract.py tests/test_orchestra_scoring.py -q
.venv/bin/python -m pytest tests/test_orchestrator_cli_entrypoints.py tests/test_orchestrator_mcp_entrypoints.py tests/test_mcp_server.py -q
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
.venv/bin/python -m pytest tests/test_orchestra_scorecard_summary.py tests/test_orchestra_state_contract.py tests/test_orchestra_scoring.py -q
# 26 passed

.venv/bin/python -m pytest tests/test_orchestrator_cli_entrypoints.py tests/test_orchestrator_mcp_entrypoints.py tests/test_mcp_server.py -q
# 16 passed

.venv/bin/python -m pytest tests/test_orchestra_*.py tests/test_private_smoke_safety.py -q
# 107 passed, 8 subtests passed

.venv/bin/python -m pytest -q
# 812 passed, 113 subtests passed

scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
# status ok, scanned_file_count=191, match_count=0

git diff --check
# clean

docker run paperorchestra-ubuntu-tools:24.04 ... orchestrator-v1-runtime
# refreshed Codex/OMX CLIs through ~/helper/update-ai-clis.sh
# installed editable package in a fresh container clone
# targeted pytest: 18 passed
# paperorchestra inspect-state includes "Score: unscored"
# paperorchestra inspect-state --json scorecard_summary.status=unscored
# MCP newline smoke with --probe-evidence-bundle: status ok, tool_count=63, mcp_probe_ok=true
```

Critic implementation validation: APPROVE.

## 6. Explicit non-goals

Slice P must not:

- call LLM Critic/model/search/OMX;
- invent scores from manuscript text;
- change readiness rules;
- let score summaries override hard gates;
- expose private/domain-specific dimension names;
- replace the full `ScholarlyScore` artifact contract from Slice O.

## 7. Stop/replan triggers

Stop and replan if:

- CLI/MCP summary implies a score means ready despite hard-gate failure;
- unknown/domain-specific dimension names appear in public output;
- tests require private material or live providers;
- implementation duplicates the full scoring rubric instead of reusing the Slice O dimension contract.
