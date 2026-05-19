# Orchestrator v1-alpha readiness snapshot

Date: 2026-05-19
Branch: `orchestrator-v1-runtime`
Head: `e47ae72 Fix demo workdir handling found during alpha audit`
Relation to `main`: `101` commits ahead, `0` behind at snapshot time
Status: **not yet final-audited for main merge**

This snapshot is a public-safe routing artifact for the v1-alpha integration
push.  It summarizes what is currently proven, what is blocked, and what must
still happen before the branch can be merged to `main`.

## 1. Objective restatement

The current objective is to reach the final audit stage for v1-alpha main
integration.  Bugs found during audit must be traceable to a command, phase,
gate, artifact/report, expected status, actual status, and resolution or known
limitation.

## 2. Current alpha hard-blocker status

| Alpha blocker | Current status | Evidence |
| --- | --- | --- |
| Git working tree clean | pending final audit recheck | This snapshot itself must be committed before the final clean-tree audit. |
| Branch behind main | pass | `main...HEAD` = `0` behind / `101` ahead |
| Full pytest | pass | `.venv/bin/python -m pytest -q` -> `1058 passed, 202 subtests passed` |
| Pre-live check | pass | `scripts/pre-live-check.sh --all` -> PASS `review/pre-live-check-20260519T094020Z` |
| Controlled smoke | pass via pre-live | `controlled_quality_gate_smoke` step completed inside pre-live |
| Mock demo explicit workdir | pass after audit fix | `./scripts/demo-mock.sh --workdir .paper-orchestra/alpha-readiness-demo` -> SUCCESS |
| Final-audit bug traceability | pass for current known bug | `paperorchestra final-audit-ledger --bugs docs/reports/orchestrator-v1-alpha-audit-bugs-20260519.json --json` -> `overall_status=pass`, `bug_count=1` |
| README/ENVIRONMENT/Skill alpha disclosure | pass | Critic-approved disclosure; docs tests pass |
| Private-safe committed evidence | pass for current slice | marker scans and pre-live `secret_scan` passed; committed bug ledger contains generic public-safe details only |
| MCP active Codex attachment | not proven in this session | raw server can be smoked with explicit venv command; local Codex config registration may be absent in this host session |
| Final fresh full live smoke | not run | explicitly reserved for final integration audit |

## 3. Current final-v1 quality gates still open

The final manuscript-quality ledger is still stricter than the v1-alpha bar.
The following families may remain open for alpha only if they remain visible and
not misrepresented as readiness:

- unsupported or weakly supported critical claims;
- citation integrity / duplicate support / citation-bomb findings;
- figure finalization warnings;
- hard gates that fail for claim/citation reasons;
- Critic consensus below `near_ready`.

These are **not** alpha merge blockers by themselves.  They become alpha blockers
only if the runtime hides them as success or fails to leave traceable evidence.

## 4. Audit bug ledger status

Current public-safe bug ledger:

- `docs/reports/orchestrator-v1-alpha-audit-bugs-20260519.json`

Current recorded bug:

- `audit-bug-demo-relative-workdir` — fixed.  The demo script now canonicalizes
  explicit workdirs before log/session creation.

Future final-audit bugs must be appended to a public-safe bug file and validated
with:

```bash
paperorchestra final-audit-ledger --bugs docs/reports/<bug-file>.json --json
```

## 5. Remaining path to main

1. Continue remaining Goal A/B/C slices with TDD-first unit/functional/fixture
   tests; do not use fresh full live smoke as the per-slice verifier.
2. Before final merge audit, re-run:

   ```bash
   .venv/bin/python -m pytest -q
   scripts/pre-live-check.sh --all
   paperorchestra final-audit-ledger --bugs docs/reports/<bug-file>.json --json
   ```

3. Run the final fresh full live smoke only at final audit time unless the user
   explicitly defers it.
4. If final audit finds bugs, record them in the bug ledger before or alongside
   fixes.
5. Merge to `main` only after the alpha hard blockers in
   `docs/reports/orchestrator-v1-alpha-merge-bar.md` are cleared and the final
   evidence bundle is public-safe.
