# Orchestrator v1 interview decisions — public-safe summary

Status: public-safe decision summary derived from private/local interview notes  
Date: 2026-05-18  
Scope: domain-general. This file intentionally omits private package names, raw local paths, raw claims, raw figure names, and private manuscript content.

## 1. Quality upgrade direction

The next PaperOrchestra runtime must improve three concerns together:

1. **Generation-first:** build a better claim/evidence structure before prose generation.
2. **Gate-first:** detect and explain manuscript-quality failures accurately.
3. **Repair-first:** make failed drafts converge toward better revisions.

A successful system loop is not the same as a submission-ready manuscript. Quality gates may correctly keep a completed run in `not_ready` when the manuscript has unsupported claims, weak source grounding, citation problems, or human-owned decisions.

## 2. Pre-writing contract

Before writing, the runtime should derive at least:

```text
source material -> source digest -> contribution model -> claim graph -> evidence obligation map -> prose writing
```

A rigid citation-intent plan is not required before writing. Citation need should be decided by the writer and quality gates using claim criticality, evidence obligations, and citation-support checks.

## 3. Human-needed semantics

`human_needed` means true author judgment is required. It must not be used for machine-solvable gaps such as missing search, missing citation support, source analysis, artifact inspection, or reference lookup.

Machine-solvable gaps should become states/actions such as:

```text
research_needed
evidence_needed
source_analysis_needed
reference_search_needed
material_gap
source_obligation_unresolved
```

User questions are allowed only for information that exists primarily in the user's head: target venue, claim priority, risk tolerance, contribution framing, or whether a weaker supported claim is acceptable.

## 4. Claim/evidence model

PaperOrchestra must keep these separate:

```text
author claim != measured evidence != validated interpretation
```

The system must be able to say that a claim is not supported by the available evidence. Suggested artifacts include author claim graphs, validated claim graphs, evidence obligations, and conflict reports.

## 5. Criticality and conflict policy

Claim criticality is driven primarily by:

- claim type: numeric, comparative, guarantee/security/proof, novelty, causal/generalizing;
- claim graph position: root claim, central contribution, abstract/conclusion dependency, many downstream claims.

Low-criticality unsupported claims may be weakened or deleted. High-criticality unsupported claims require additional research/evidence or author judgment, and may keep the manuscript blocked.

## 6. Scholarly scoring policy

Scores diagnose quality, prioritize repair, and measure progress. Hard gates decide what cannot pass.

Accepted dimensions:

1. `claim_validity`
2. `evidence_claim_calibration`
3. `source_grounding`
4. `citation_integrity`
5. `contribution_and_novelty`
6. `experimental_interpretation`
7. `scope_and_limitations`
8. `argument_structure`
9. `technical_specificity`
10. `prose_and_terminology`
11. `reproducibility_surface`

Rejected dimension: `reviewer_attack_surface`, because it can encourage overly defensive manuscripts.

Scoring should be evidence-bundled and Critic-centered. Deterministic code should validate bundle completeness, freshness, hard gates, citation density, duplicate support, metadata, reproducibility, and compile facts.

## 7. Phase-specific scoring

The runtime should support phase-specific bundles and scores:

- prewriting: is the claim/evidence structure ready to write?
- section/in-writing: does a section follow obligations without adding unsupported high-risk claims?
- revision: did a candidate improve the manuscript without new blockers?
- final: is the full manuscript ready for human finalization?

Hard gate failure keeps readiness at `not_ready` regardless of score.

## 8. Notice-first autonomy and author override

Before claim-safe live writing, show an interruptible prewriting notice with the author-responsible claims, evidence status, and intended direction. Proceed unless interrupted.

If the author interrupts, capture author intent and re-adjudicate the claim/evidence graph. Do not directly mutate validated evidence based only on author assertion.

An author may insist on keeping an unsupported claim, but the manuscript readiness remains BLOCK/not_ready until adequate evidence or a safe rewrite exists.

## 9. Figure/plot gate

Figure handling must be generic. Evidence plots require hard gating for data provenance, claim alignment, caption safety, visual integrity, text-plot consistency, and necessity/redundancy.

User-supplied figures should be inventoried and matched to manuscript slots when semantically safe. Ambiguous or missing matches should become human-finalization blockers, not silent placeholder success.

## 10. State-machine and orchestrator architecture

Use a hierarchical/parallel state-contract architecture rather than one flat FSM. `OrchestraState` is the canonical world model and `OrchestraOrchestrator` is the top-level runtime coordinator, but domain work remains delegated to bounded services.

Required components:

- `OrchestraState`
- `StateBuilder`
- `StateValidator`
- `ReadinessPolicy`
- `InteractionPolicy`
- `ActionPlanner`
- `ActionExecutor`
- `OrchestraOrchestrator`

## 11. First-user product flow

PaperOrchestra is a Codex/OMX-wrapped paper-writing solution, not just a CLI command collection. First users may ask natural-language prompts such as setup, how to use it, or to write a paper. The agent should guide them through intake, state inspection, scorecards, and next actions without dumping README content.

## 12. OMX integration policy

If a stage claims OMX-backed execution, it must emit explicit invocation/evidence artifacts. Core product-runtime surfaces are:

- `$autoresearch`
- `$autoresearch-goal`
- `$deep-interview`
- `$ralplan`
- `$ralph`
- `$ultraqa`
- `$trace`

Core direct-call surfaces include `omx exec`, `omx state`, `omx trace`, `omx explore`, `omx sparkshell`, and basic status/version/doctor/help probes.

Deprecated legacy `omx autoresearch` is forbidden. `$team`, `$ultrawork`, and `$ultragoal` are not v1 manuscript-runtime primitives.

## 13. Private final-smoke policy

A private reference package may be used outside the public repo for final smoke quality assessment, but it is not an implementation fixture, training target, structure target, or wording target.

Public implementation, tests, prompt assets, and documentation must remain domain-general. Any domain-specific shortcut, fixture, prompt wording, filename dependency, or acceptance metric is a BLOCK.

Public-safe final-smoke evidence may contain counts, hashes, generic status labels, and redacted references only. It must not contain private manuscript text, private claims, private figure names, private bibliography entries, raw local paths, or author-identifying details.

## 14. MCP issue ordering

MCP/Codex attach compatibility is a first-class blocker because MCP/Skill is the primary user surface. The main-branch framing/attach fix must remain the base for the v1 branch, and v1 readiness must distinguish config registration, raw MCP health, newline/content-length transport smoke, Codex attach smoke, and current conversation tool visibility.

## 15. Final acceptance constraints

The v1 line is not complete until current evidence proves:

- tests and state/action contracts pass;
- MCP/Skill smoke is current;
- mock demo, compile/export, and container smoke pass;
- private final live smoke is redacted and public-safe;
- no unsupported critical claim remains;
- no unknown references support cited critical claims;
- citation integrity passes or leaves only non-critical warnings;
- supplied figures are inventoried and matched/replaced where safe, or explicitly blocked for human finalization;
- hard gates do not fail except final human-only polish/submission tier;
- Critic consensus says near-ready or better;
- Verifier confirms evidence completeness and no private leakage;
- exported PDF, TeX, and evidence bundle exist;
- README/ENVIRONMENT/Skill docs explain the orchestrated runtime.
