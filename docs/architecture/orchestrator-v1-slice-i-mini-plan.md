# Slice I mini-plan — public-safe evidence research mission planner

Status: implemented; plan and implementation validated by Critic before commit
Date: 2026-05-13
Branch: `orchestrator-v1-runtime`

## 1. Target result

Turn candidate claim/evidence/citation obligations into a public-safe machine-research mission:

```text
claim graph report
-> evidence research mission
-> standard research route: $autoresearch
-> durable novelty/causal route: $autoresearch-goal
-> OrchestraState evidence facet + next action
```

This slice still does not run live research. It prepares the mission and proves the routing is machine-solvable, explicit, redacted, and testable.

## 2. Why this slice exists

The user-visible failure we are hardening against is unsupported/unknown references and unrelated writing. After Slice H, PaperOrchestra can identify candidate claims and obligations. It now needs a generic bridge that says:

- what must be researched;
- whether ordinary `$autoresearch` is enough;
- whether durable `$autoresearch-goal` is required;
- which claim/citation obligations caused the route;
- why this is not a `human_needed` question yet.

## 3. Public module and integration points

Proposed file:

```text
paperorchestra/orchestra_research.py
```

Types/functions:

```text
ResearchTask
EvidenceResearchMission
build_evidence_research_mission(claim_graph)
```

Integrate conservatively with:

```text
paperorchestra/orchestrator.py
```

`run_until_blocked(..., material_path=...)` may attach a public-safe `evidence_research_mission` evidence ref after building a claim graph and set:

- `evidence=research_needed` for standard support/citation tasks;
- `evidence=durable_research_needed` when novelty/causal high-critical tasks need a durable research loop;
- next action from the existing `ActionPlanner` (`start_autoresearch` or `start_autoresearch_goal`).

## 4. Generic routing policy

- Numeric/comparative/method/background obligations are standard machine research by default.
- Novelty or causal high-critical obligations require durable research (`$autoresearch-goal`) by default.
- Citation support tasks are machine-solvable until a later verifier/critic finds a real strategic conflict.
- No task may route to `human_needed` merely because a reference is unknown or evidence is missing.

## 5. Public-safe policy

The mission public payload may include:

- task IDs;
- task type (`evidence_support`, `citation_support`);
- claim ID/type/role/criticality;
- claim text hash/redacted label;
- citation obligation IDs;
- desired OMX surface (skill surface only, not an executable command);
- execution status, which must be `planned_only` in this slice;
- compact reason codes.

The mission public payload must not include raw private claim text, raw source text, private paths, titles, BibTeX bodies, or domain-specific names by default.

It also must not emit the deprecated direct command string `omx autoresearch`. The standard route is the `$autoresearch` skill surface; durable routes use `$autoresearch-goal`.

## 6. Tests to add first

Proposed file:

```text
tests/test_orchestra_research_mission.py
```

Minimum tests:

1. mission redacts raw claim text but preserves task/claim hashes;
2. numeric/comparative obligations choose standard `$autoresearch`;
3. novelty/causal high-critical obligations choose durable `$autoresearch-goal`;
4. unknown citation support remains machine-solvable and does not create `human_needed`;
5. public mission payload distinguishes `desired_surface` from executable command and records `execution_status=planned_only`;
6. public mission payload never contains deprecated `omx autoresearch`;
7. empty/no-obligation graph produces a ready no-op mission;
8. `run_until_blocked(material_path=...)` with synthetic novelty material records `evidence_research_mission` and routes to `start_autoresearch_goal` without drafting.

## 7. Validation for this slice

Required before commit/push:

```bash
.venv/bin/python -m pytest tests/test_orchestra_research_mission.py tests/test_orchestra_claims.py tests/test_orchestra_draft_control.py -q
.venv/bin/python -m pytest tests/test_orchestra_materials.py tests/test_orchestra_state_scenarios.py tests/test_orchestrator_cli_entrypoints.py tests/test_orchestrator_mcp_entrypoints.py -q
.venv/bin/python -m pytest tests/test_orchestra_*.py tests/test_private_smoke_safety.py -q
git diff --check
```

Preferred:

```bash
.venv/bin/python -m pytest -q
scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
```

Critic plan validation is required before implementation. Critic implementation validation is required before commit.

Implementation evidence captured before commit:

- initial test run failed before implementation with missing `paperorchestra.orchestra_research`
- research mission + claim/draft-control tests: passed
- material/state/CLI/MCP targeted tests: passed
- orchestrator-family + private-smoke safety tests: passed
- full test suite: passed
- private leakage scan against local denylist: passed with zero matches
- Critic implementation verdict: APPROVE

## 8. Explicit non-goals

Slice I must not:

- execute OMX;
- call web/Semantic Scholar/model providers;
- mark evidence as supported;
- mark citations as supported;
- ask the human to fill machine-solvable evidence gaps;
- introduce domain-specific/private rules;
- draft or revise manuscript prose.

## 9. Stop/replan triggers

Stop and replan if:

- mission construction requires raw private text in public output;
- unknown references route to `human_needed`;
- claim candidates are promoted to validated/supported;
- the route depends on private/domain-specific terminology;
- tests require actual private material;
- OMX execution is attempted in unit tests.
- public mission payload contains `omx autoresearch` or otherwise looks like an executed command instead of planned-only routing.
