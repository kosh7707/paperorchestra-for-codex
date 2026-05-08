# M0 ownership lock — strict review quality-gate hardening

This tracked note records the canonical source owners for the strict-review
quality-gate hardening tranche. It exists as a public, version-controlled
ownership lock for scripts and modules that enforce quality-gate behavior.

## Source-plan status

The original planning artifacts were internal workflow notes and are not part
of the public repository. This document is the tracked public contract: update
it when canonical owner files change, and keep the path stable because
`controlled-quality-gate-smoke.py` checks it.

## Tracked canonical owners

- Live claim-safe smoke/export owner: `scripts/live-smoke-claim-safe.sh`
  - Records command/stdout/stderr/exit-code evidence.
  - Writes final verdict/exit code and artifact manifest.
  - Copies canonical session artifacts into the evidence bundle.
- Pre-live policy gate owner: `scripts/pre-live-check.sh`
  - Enforces claim-safe/web-evidence command tokens before live smoke.
- QA/evidence identity owners:
  - `paperorchestra/quality_loop.py`
  - `paperorchestra/quality_loop_citation_support.py`
  - `paperorchestra/quality_loop_history.py`
  - `paperorchestra/operator_feedback.py`
  - `paperorchestra/ralph_bridge_handoff.py`
- Claim-safe evidence defaults owners:
  - `paperorchestra/operator_feedback.py`
  - `paperorchestra/cli.py`
  - `paperorchestra/mcp_server.py`
  - `paperorchestra/ralph_bridge.py`

## Ignored/evidence-only artifacts

Ignored `review/` scripts and bundles are local audit outputs, not tracked
canonical harness owners.
No M0/A4 fix may be applied only to ignored `review/` evidence artifacts.

## Decision

Proceed with A1-A5 only against tracked source/scripts/tests above. If an
operator-feedback counter fix requires logic that exists only in ignored review
scripts, stop and replan instead of patching evidence.
