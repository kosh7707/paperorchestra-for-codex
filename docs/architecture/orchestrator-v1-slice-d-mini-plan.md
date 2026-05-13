# Slice D mini-plan — full-loop gate skeleton, scoring bundles, and consensus routing

Status: slice implementation plan requiring Critic validation before code
Date: 2026-05-13
Branch: `orchestrator-v1-runtime`

## 1. Target result

Slice D is too large to implement in one unsafe jump. This mini-plan defines **Slice D1**, the first bounded full-loop substrate:

```text
draft/state facts
-> figure gate skeleton
-> scoring input bundle skeleton
-> Critic consensus artifact skeleton
-> repair / human_needed / compile-export action routing
```

D1 remains deterministic and testable with fake artifacts. It does not invoke real LLM Critic, real OMX, real search, real compile, or private material.

The goal is to make later real loop execution impossible to wire without the required artifacts and hard-gate semantics.

## 2. Public modules to add or extend

Proposed files:

```text
paperorchestra/orchestra_figures.py
paperorchestra/orchestra_scoring.py
paperorchestra/orchestra_consensus.py
paperorchestra/orchestra_loop.py
```

Extend:

```text
paperorchestra/orchestra_state.py
paperorchestra/orchestra_planner.py
```

## 3. D1 responsibilities

### 3.1 Figure gate skeleton

Generic only. Use synthetic fixtures.

Types:

```text
FigureAsset
FigureSlot
FigureMatchDecision
FigureGateReport
FigureGatePolicy
```

Rules:

- supplied assets must be inventoried before placeholders are accepted;
- safe semantic match may mark a slot matched;
- ambiguous/no match records `human_finalization_needed` or `blocked`;
- placeholder-only final state cannot silently pass;
- provenance uses paths/hashes, but public-safe export can redact filenames when necessary.

### 3.2 Scoring input bundle skeleton

Types:

```text
ScoringInputBundle
ScoringBundleBuilder
ScholarlyScore
```

Rules:

- bundle is phase-specific: `prewriting`, `section`, `revision`, `final`;
- bundle binds to `manuscript_sha256`;
- missing required artifacts blocks scoring;
- bundle includes compressed evidence refs, not raw private material;
- score output without evidence links is invalid;
- scores diagnose and prioritize repair, but cannot override hard gates.

### 3.3 Critic consensus artifact skeleton

Types:

```text
CriticVerdict
CriticConsensus
ConsensusPolicy
```

Rules:

- high-risk readiness needs at least two Critic verdicts;
- if two verdicts disagree after consensus attempts, plan third adjudication;
- final consensus must preserve evidence links and blocker reasons;
- Verifier is not implemented in D1, but D1 must plan `verifier_check` / `record_trace_summary` style actions for later.

### 3.4 Loop planner skeleton

`FullLoopPlanner` or extension of `ActionPlanner` should route:

- hard gate fail -> `repair_needed` / `start_ralph` or high-risk `start_ralplan`;
- scoring bundle missing -> `build_scoring_bundle`;
- critic consensus missing for high-risk readiness -> `run_critic_consensus`;
- consensus disagreement -> `run_third_critic_adjudication`;
- figure placeholder unresolved -> `match_supplied_figures` or `human_needed` blocker;
- ready + compiled missing -> `compile_current`;
- compiled + export missing -> `export_results`.

No real execution occurs in D1. It is action planning plus contract artifacts.

## 4. Tests to add first

Proposed files:

```text
tests/test_orchestra_figures.py
tests/test_orchestra_scoring.py
tests/test_orchestra_consensus.py
tests/test_orchestra_full_loop_planner.py
```

Minimum failing tests before implementation:

1. figure inventory records supplied generic assets with hashes;
2. safe figure/slot semantic match marks slot matched;
3. ambiguous figure match does not replace placeholder and records human-finalization blocker;
4. placeholder-only figure state blocks final readiness;
5. scoring bundle binds to manuscript hash and required artifact refs;
6. missing required scoring artifact blocks score generation;
7. Critic score without evidence links is rejected;
8. hard gate fail overrides high score in loop planner;
9. two agreeing Critic verdicts produce consensus pass/near_ready;
10. two disagreeing Critic verdicts plan third adjudication;
11. high-risk readiness without consensus plans `run_critic_consensus`;
12. compile/export actions are planned only after hard gates and consensus allow it;
13. public-safe scoring/consensus exports omit private raw text;
14. no deprecated `omx autoresearch` action appears.

## 5. Validation for D1

Required before commit/push:

```bash
.venv/bin/python -m pytest \
  tests/test_orchestra_figures.py \
  tests/test_orchestra_scoring.py \
  tests/test_orchestra_consensus.py \
  tests/test_orchestra_full_loop_planner.py \
  tests/test_orchestra_draft_control.py \
  tests/test_orchestra_state_contract.py \
  tests/test_orchestra_state_scenarios.py \
  tests/test_orchestra_action_planner.py -q
.venv/bin/python -m pytest tests/test_mcp_server.py tests/test_pre_live_check_script.py -q
git diff --check
```

Preferred:

```bash
.venv/bin/python -m pytest -q
```

Critic implementation validation is required before commit.

## 6. Explicit non-goals

D1 must not:

- invoke live LLM Critic or Verifier;
- invoke real OMX;
- compile PDFs;
- export final bundles;
- run private final smoke;
- add MCP tools;
- add real figure rendering/replacement in TeX;
- add domain/private-specific tests, filenames, prompts, or acceptance metrics.

## 7. Stop/replan triggers

Stop and replan if:

- score can override a hard gate;
- figure placeholders can silently pass;
- consensus can pass without evidence links;
- public-safe exports include raw private text;
- D1 starts doing real LLM/OMX work instead of planning/evidence skeleton;
- test fixtures drift toward private/domain-specific material.
