# PaperOrchestra v1 OrchestraState contract

Status: implementation-gating contract for `orchestrator-v1-runtime` branch
Date: 2026-05-13
Scope: public, domain-general state and transition contract.

## 1. Purpose

`OrchestraState` is the canonical PaperOrchestra world model. It is not a display-only status object and not a single flat enum. It is a versioned snapshot composed from orthogonal facets, artifact hashes, policy decisions, and next valid actions.

The first implementation slice must make this contract testable before wiring production runtime paths through it.

## 2. Required top-level fields

Minimum schema for v1 skeleton:

```json
{
  "schema_version": "orchestra-state/1",
  "cwd": "...",
  "session_id": "... | null",
  "manuscript_sha256": "... | null",
  "facets": {},
  "hard_gates": {},
  "scores": {},
  "readiness": {},
  "five_axis_status": {},
  "blocking_reasons": [],
  "next_actions": [],
  "evidence_refs": [],
  "private_safe": true
}
```

`private_safe=true` means the exported state contains only public-safe summaries, hashes, counts, and paths that are allowed for the current export mode. It does not mean the underlying project has no private material.

## 3. Facet axes and allowed values

Initial implementation may leave some facets at `unknown`/`not_checked`, but it must never invent a ready state for an unchecked facet.

| Facet | Allowed values | Notes |
| --- | --- | --- |
| `session` | `no_session`, `initialized`, `draft_available`, `compiled`, `blocked` | Mirrors current `SessionState`/artifacts without pretending exhaustive legacy phases. |
| `material` | `missing`, `inventory_needed`, `inventoried_insufficient`, `inventoried_sufficient`, `blocked` | User material sufficiency, not final paper quality. |
| `source_digest` | `missing`, `stale`, `ready`, `blocked` | Digest must be hash-bound to material inventory. |
| `claims` | `missing`, `candidate`, `validated`, `conflict`, `blocked` | Supports dual author/validated graph later. |
| `evidence` | `missing`, `research_needed`, `durable_research_needed`, `supported`, `unresolved`, `blocked` | Machine-solvable before human escalation. |
| `citations` | `not_checked`, `unknown_refs`, `unsupported_critical`, `warnings_only`, `supported` | Unknown critical references block readiness. |
| `figures` | `not_checked`, `inventory_needed`, `placeholder_only`, `matched`, `human_finalization_needed`, `blocked` | Supplied figures must be inventoried before placeholders are silently accepted. |
| `writing` | `not_allowed`, `prewriting_notice_pending`, `drafting_allowed`, `draft_available`, `revision_candidate` | Drafting requires prewriting notice and evidence policy satisfaction. |
| `quality` | `not_evaluated`, `hard_gate_failed`, `repairable`, `near_ready`, `human_finalization_candidate` | Scores cannot override hard gates. |
| `interaction` | `none`, `notice_required`, `research_needed`, `human_needed`, `answered`, `interrupted` | `human_needed` is author judgment only. |
| `omx` | `not_required`, `required_missing`, `in_progress`, `evidence_present`, `degraded`, `failed` | Strict OMX mode blocks if evidence is missing. |
| `artifacts` | `unknown`, `missing_required`, `stale`, `fresh` | Hash/freshness facts for load-bearing artifacts. |

## 4. Events and derivation vocabulary

StateBuilder may derive facets from artifacts; ActionPlanner emits actions from state. Use a small event/action vocabulary so tests do not guess.

### 4.1 Intake and source events

```text
material_path_provided
material_inventory_built
material_insufficient
source_digest_built
source_digest_stale
```

### 4.2 Claim/evidence events

```text
claim_candidates_built
claim_graph_validated
claim_evidence_conflict_detected
evidence_gap_detected
evidence_support_found
critical_evidence_unresolved
```

### 4.3 Research and human events

```text
autoresearch_required
autoresearch_goal_required
autoresearch_passed
autoresearch_failed
human_needed_packet_built
human_answer_imported
user_interrupted
re_adjudication_required
```

### 4.4 Writing/quality events

```text
prewriting_notice_built
prewriting_notice_acknowledged
draft_generation_started
draft_generated
quality_eval_built
critic_consensus_built
repair_candidate_built
repair_candidate_promoted
```

### 4.5 Citation/figure/compile/export events

```text
citation_review_built
unknown_reference_detected
critical_citation_supported
figure_inventory_built
figure_slot_match_built
placeholder_figure_unresolved
compile_succeeded
export_succeeded
```

### 4.6 OMX evidence events

```text
omx_action_planned
omx_invocation_recorded
omx_invocation_failed
trace_summary_recorded
```

## 5. Readiness labels

`readiness.label` must be one of:

```text
no_session
needs_material
intake_needed
research_needed
human_needed
draft_blocked
ready_for_drafting
repair_needed
not_ready
ready_for_human_finalization
failed
```

Rules:

- `ready_for_human_finalization` is the highest automated manuscript state.
- No state is called `submission_ready` or `success`.
- `failed` means no safe automatic recovery path is currently known.
- `research_needed` is machine-solvable and should route to search/autoresearch before asking the author.
- `human_needed` means author judgment is required.

## 6. Five-axis user status mapping

The user-facing compact status card should expose exactly five axes by default. These axes summarize detailed facets without replacing them.

| Axis | Derived from | Values |
| --- | --- | --- |
| `materials` | `material`, `source_digest` | `missing`, `insufficient`, `ready`, `blocked` |
| `claims` | `claims`, `evidence` | `missing`, `needs_research`, `conflict`, `supported`, `blocked` |
| `citations` | `citations`, `evidence` | `not_checked`, `unknown_refs`, `unsupported`, `warnings`, `supported` |
| `figures` | `figures` | `not_checked`, `needs_inventory`, `placeholder`, `matched`, `human_polish`, `blocked` |
| `readiness` | `quality`, hard gates, `interaction` | `not_ready`, `draft_blocked`, `research_needed`, `human_needed`, `repair_needed`, `near_ready`, `ready_for_human_finalization` |

The status card is advisory. It must not hide hard blockers.

## 7. Hard invariants

StateValidator must reject or downgrade states violating these invariants.

1. Hard gate failure implies `readiness.label != ready_for_human_finalization`.
2. `quality=near_ready` or `human_finalization_candidate` is invalid when `hard_gates.status != pass`.
3. `writing=drafting_allowed` requires `material=inventoried_sufficient`, `source_digest=ready`, and `writing` previously or currently acknowledges `prewriting_notice_pending`.
4. `interaction=human_needed` is invalid for purely machine-solvable citation/search/source gaps.
5. `evidence=research_needed` must plan `$autoresearch` or equivalent search before `human_needed`.
6. `evidence=durable_research_needed` must plan `$autoresearch-goal` before readiness can unblock.
7. Strict `omx` mode with missing invocation evidence implies `readiness.label=not_ready` or `research_needed`/`repair_needed`, never ready.
8. Unknown references supporting critical claims imply `citations=unknown_refs` and readiness block.
9. Unsupported critical citations imply `citations=unsupported_critical` and readiness block.
10. Placeholder figures after figure phase require either `figures=human_finalization_needed` or `figures=blocked`; they cannot be silently treated as complete.
11. Author override cannot force readiness when evidence contradicts or fails to support the claim.
12. User interrupt after a notice or human-needed packet forces `interaction=interrupted` and plans `re_adjudicate`, not silent continuation.
13. Stale artifacts bound to an old manuscript hash cannot support current readiness.
14. Public-safe export must not include raw private material, private filenames, private claims, private BibTeX, or private figure names.
15. Deprecated `omx autoresearch` must never appear in planned or recorded actions.

## 8. `research_needed` vs `human_needed`

### 8.1 `research_needed`

Use when the system can act without author judgment:

- find sources for a background claim;
- verify citation metadata;
- search for related work;
- investigate novelty uncertainty;
- validate whether a paper supports a sentence;
- fill missing citation support evidence.

Next actions should be `$autoresearch`, `$autoresearch-goal`, web/S2 search, citation support review, or safe claim weakening candidate.

### 8.2 `human_needed`

Use only when author judgment is required:

- keep or weaken a central risky claim;
- choose contribution framing;
- decide if additional experiments/materials can be provided;
- accept a weaker but supported contribution;
- resolve a strategic conflict where evidence does not support the user’s desired claim.

A `human_needed` packet must include:

- the conflict/question;
- evidence summary;
- available options;
- consequences;
- recommended default if the user does not answer;
- next valid action after answer.

## 9. Author override policy

An author may disagree with PaperOrchestra, but the override has bounded effects.

Allowed:

- preserve author intent in `author_claim_graph`;
- request more research;
- choose a weaker/stronger supported framing;
- mark a claim as intentionally speculative if evidence and venue norms permit.

Forbidden:

- mark unsupported critical claims as ready;
- bypass fake/Unknown reference gates;
- bypass private leakage gates;
- promote a candidate that regresses hard blockers;
- call a manuscript submission-ready.

If author override conflicts with evidence, state must record:

```text
interaction=answered
claims=conflict or blocked
readiness=not_ready or human_needed
blocking_reason=author_override_conflicts_with_evidence
```

## 10. Prewriting notice and interrupt policy

Before drafting, PaperOrchestra must show a concise prewriting notice:

- what material was found;
- what claim/evidence structure will be used;
- known gaps;
- whether research will run;
- what will be asked only if necessary;
- how the user can interrupt.

If the user interrupts after the notice, the orchestrator must plan `re_adjudicate` and rebuild state from the new instruction. It must not continue with the previous plan silently.

## 11. Figure gate effects

Figure gate status affects readiness but should not overclaim failure.

Rules:

- No figure assets supplied and placeholders remain -> `figures=placeholder_only`; readiness may be `human_finalization_needed` if scholarly claims are otherwise supported.
- Supplied assets exist but were not inventoried -> `figures=inventory_needed`; block final readiness.
- Safe semantic match found -> `figures=matched`; record provenance.
- Ambiguous match -> do not replace; record blocker and next action.
- Final artwork/layout polish can remain a human-finalization blocker without failing all claim-safe logic.

## 12. Minimal first test files

Implementation must begin with tests matching this contract.

Required initial files:

```text
tests/test_orchestra_state_contract.py
tests/test_orchestra_state_scenarios.py
tests/test_orchestra_action_planner.py
```

Minimum first failing tests:

1. state JSON round-trip with facet defaults;
2. hard gate fail overrides high score;
3. machine-solvable citation gap routes to `research_needed`, not `human_needed`;
4. durable research gap plans `$autoresearch-goal`;
5. high-risk claim/evidence conflict routes to `human_needed`;
6. author override cannot force readiness;
7. prewriting notice required before drafting;
8. user interrupt plans re-adjudication;
9. figure placeholder without report blocks or human-finalization-blocks readiness;
10. deprecated `omx autoresearch` is impossible in action output.
