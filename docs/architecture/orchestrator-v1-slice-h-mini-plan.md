# Slice H mini-plan — generic claim graph and evidence-obligation skeleton

Status: implemented; plan and implementation validated by Critic before commit
Date: 2026-05-13
Branch: `orchestrator-v1-runtime`

## 1. Target result

Turn public-safe material inventory/source digest evidence into a generic claim/evidence planning surface:

```text
material path
-> material inventory + source digest
-> candidate claim graph skeleton
-> evidence/citation obligation skeleton
-> OrchestraState claims/evidence/citation facets
-> next action: start machine research, request stronger material, or show prewriting notice later
```

This slice is deterministic and local. It does not call LLMs, web search, Semantic Scholar, OMX, or manuscript drafting.

## 2. Public module and integration points

Proposed file:

```text
paperorchestra/orchestra_claims.py
```

Types/functions:

```text
ClaimCandidate
EvidenceObligation
CitationObligation
ClaimGraphReport
build_claim_graph_from_materials(material_path, inventory, digest)
```

Integrate conservatively with:

```text
paperorchestra/orchestrator.py
paperorchestra/orchestra_draft_control.py
```

`run_until_blocked(..., material_path=...)` may build a claim/evidence skeleton after sufficient material exists. `inspect_state` should stay bounded and public-safe; any raw claim text must be redacted in public dictionaries.

## 3. Generic extraction policy

The first implementation may use deterministic generic text signals only:

- numeric/comparative/novelty/causal/method/background claim type hints;
- graph roles: `root`, `central_support`, `local`, `background`;
- criticality derived from existing draft-control policy concepts;
- source refs are material file hashes/redacted labels, not raw private paths.

This is not a citation-intent plan and not a final claim verifier. It is an obligation builder that says what must be checked before drafting.

## 4. Public-safe policy

Internal objects may carry raw synthetic/private claim text for downstream processing, but default public export must include only:

- claim IDs;
- claim type, graph role, criticality;
- text hash/redacted claim label;
- source file hash/redacted source label;
- obligation status and machine-solvable routing.

No raw private claim, title, figure name, author name, dataset name, or domain-specific token may appear in public state/evidence by default.

## 5. Tests to add first

Proposed file:

```text
tests/test_orchestra_claims.py
```

Minimum tests:

1. generic text with numeric/comparative/novelty/method signals yields typed claim candidates;
2. public claim graph redacts raw claim text while preserving hashes and IDs;
3. high-criticality candidates create machine-solvable evidence and citation obligations;
4. low/background unsupported candidates are not routed to `human_needed`;
5. insufficient material cannot build a ready claim graph;
6. `run_until_blocked(material_path=...)` with sufficient synthetic material progresses from digest to claim/evidence planning without drafting;
7. public fixtures use synthetic/generic text only.

## 6. Validation for this slice

Required before commit/push:

```bash
.venv/bin/python -m pytest tests/test_orchestra_claims.py tests/test_orchestra_draft_control.py -q
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

- initial test run failed before implementation with missing `paperorchestra.orchestra_claims`
- claim/draft-control targeted tests: passed
- material/state/CLI/MCP targeted tests: passed
- orchestrator-family + private-smoke safety tests: passed
- full test suite: passed
- private leakage scan against local denylist: passed with zero matches
- Critic implementation verdict: APPROVE

## 7. Explicit non-goals

Slice H must not:

- perform live citation/reference validation;
- use Semantic Scholar/web search;
- ask humans for source/citation gaps;
- make drafting allowed merely because candidates exist;
- introduce CCI/private/domain-specific rules;
- emit raw private claim text in public state;
- replace the later Critic/score/quality gates.

## 8. Stop/replan triggers

Stop and replan if:

- claim extraction requires domain-specific terms;
- public state leaks raw private text by default;
- machine-solvable evidence gaps route to `human_needed`;
- candidate claims are labeled `validated` without evidence;
- drafting becomes allowed before obligations pass;
- tests require actual private material.
