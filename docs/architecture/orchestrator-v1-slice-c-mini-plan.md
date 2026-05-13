# Slice C mini-plan — draft-control policy and evidence-obligation routing

Status: slice implementation plan requiring Critic validation before code  
Date: 2026-05-13  
Branch: `orchestrator-v1-runtime`

## 1. Target result

Implement the first draft-control layer on top of the Slice B `OrchestraState` substrate:

```text
claim/evidence/citation facts
-> draft-control policy
-> draft_allowed | research_needed | human_needed | blocked
-> deterministic ActionPlanner routing
```

This slice decides whether PaperOrchestra may proceed toward drafting, must research more, must ask the author, or must block.

It remains pre-writing/draft-control only. It does **not** write the manuscript, invoke real web/S2 search, run real OMX, rewrite MCP/Skill, or run private final smoke.

## 2. Public modules to add or extend

Proposed file:

```text
paperorchestra/orchestra_draft_control.py
```

Proposed types:

```text
ClaimSignal
EvidenceObligationSignal
CitationObligationSignal
DraftControlInput
DraftControlDecision
DraftControlPolicy
```

Extend existing modules only as needed:

```text
paperorchestra/orchestra_state.py
paperorchestra/orchestra_policies.py
paperorchestra/orchestra_planner.py
```

## 3. Draft-control concepts

### 3.1 Claim signal

Generic, domain-independent claim metadata:

```json
{
  "claim_id": "C1",
  "claim_type": "numeric | comparative | security | novelty | causal | background | method | limitation",
  "graph_role": "root | central_support | local | background",
  "evidence_status": "missing | supported | conflict | contradicted | unknown",
  "author_desired_strength": "strong | moderate | weak | unspecified"
}
```

Do not store private raw claim text in public-safe tests. Synthetic tests may use generic text such as `synthetic throughput claim`.

### 3.2 Evidence obligation signal

```json
{
  "obligation_id": "E1",
  "claim_id": "C1",
  "status": "missing | research_needed | durable_research_needed | supported | conflict | contradicted",
  "machine_solvable": true
}
```

### 3.3 Citation obligation signal

```json
{
  "obligation_id": "R1",
  "claim_id": "C1",
  "status": "not_checked | unknown_reference | unsupported | supported | warning",
  "critical": true
}
```

No rigid citation-intent plan is introduced. The policy evaluates obligation/support facts and routes work; it does not pre-template exact citation placement.

## 4. Policy rules

### 4.1 Criticality

Criticality is derived mainly from claim type and graph role:

High criticality:

- `numeric`, `comparative`, `security`, `novelty`, `causal` claim types;
- `root` or `central_support` graph role.

Medium:

- `method` or `limitation` claim types;
- local role with downstream support.

Low:

- background/local claims without central dependency.

### 4.2 Routing

Rules:

1. Missing claim graph -> `build_claim_graph`.
2. Missing evidence obligation map -> `build_evidence_obligations`.
3. Machine-solvable missing support -> `research_needed` + `start_autoresearch`.
4. Durable/novelty/background investigation -> `durable_research_needed` + `start_autoresearch_goal`.
5. Unknown/unsupported reference for a critical claim -> block drafting and route research/citation support.
6. High-criticality conflict or contradiction -> `human_needed` + `start_deep_interview` after bounded research facts are recorded.
7. Low-criticality unsupported background claim -> auto-weaken/delete candidate action, not human_needed.
8. Supported obligations + no hard blockers -> `show_prewriting_notice` before any draft action.
9. Prewriting notice acknowledged -> `drafting_allowed`.
10. Author override cannot bypass critical evidence/citation blockers.

## 5. Tests to add first

Proposed file:

```text
tests/test_orchestra_draft_control.py
```

Minimum failing tests before implementation:

1. missing claim graph plans `build_claim_graph`;
2. missing evidence obligations plan `build_evidence_obligations`;
3. machine-solvable evidence gap returns `research_needed` and `start_autoresearch`, not `human_needed`;
4. durable/novelty evidence gap returns `start_autoresearch_goal`;
5. critical Unknown reference blocks drafting;
6. high-criticality conflict routes to `human_needed` / `start_deep_interview`;
7. low-criticality unsupported background claim plans auto-weaken/delete rather than human_needed;
8. supported obligations require prewriting notice before drafting;
9. acknowledged prewriting notice allows `drafting_allowed`;
10. author override cannot bypass critical blockers.

Existing Slice B tests must continue to pass.

## 6. Validation for this slice

Required before commit/push:

```bash
.venv/bin/python -m pytest \
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

## 7. Explicit non-goals

This slice must not:

- write or revise manuscript prose;
- call real web/S2 search;
- call real OMX;
- add citation-intent placement templates;
- add CCI/private-specific fixtures or logic;
- expose new MCP tools;
- weaken hard gates or readiness semantics.

## 8. Stop/replan triggers

Stop and replan if:

- the policy needs raw private claim text to pass tests;
- low-criticality auto-weaken logic risks deleting central claims;
- `human_needed` starts catching source/citation gaps that are machine-solvable;
- author override is allowed to bypass critical citation/evidence failure;
- the draft-control policy begins generating prose rather than planning.
