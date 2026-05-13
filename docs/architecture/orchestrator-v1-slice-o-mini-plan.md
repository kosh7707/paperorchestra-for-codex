# Slice O mini-plan — scholarly scorecard rubric contract

Status: implemented and Critic-approved
Date: 2026-05-13
Branch: `orchestrator-v1-runtime`

## 1. Target result

The orchestrator currently has a minimal scoring skeleton (`overall`, `readiness_band`, `evidence_links`). Slice O turns that into a public, general-purpose scholarly scorecard contract that later LLM Critic scoring can fill:

```text
phase evidence bundle -> 11-dimension scholarly scorecard -> compact score/status card
```

This slice remains deterministic/schema-level. It does not ask a model to score and does not execute live research.

## 2. Rubric dimensions

The scorecard must include the accepted general dimensions from the interview output:

```text
claim_validity
evidence_claim_calibration
source_grounding
citation_integrity
contribution_and_novelty
experimental_interpretation
scope_and_limitations
argument_structure
technical_specificity
prose_and_terminology
reproducibility_surface
```

It must explicitly exclude/reject `reviewer_attack_surface`, because that dimension incentivizes defensive claim weakening rather than well-grounded strong claims.

## 3. Scope

Extend:

```text
paperorchestra/orchestra_scoring.py
tests/test_orchestra_scoring.py
tests/test_orchestra_full_loop_planner.py
docs/architecture/orchestrator-v1-slice-o-mini-plan.md
```

Public additions:

```text
SCORE_DIMENSIONS
ScoreDimensionAssessment
ScholarlyScore.to_public_dict()
ScholarlyScore.to_summary()
render_compact_scorecard(score, blockers=optional)
```

## 4. Required behavior

- every dimension assessment must include score, confidence, rationale, evidence links, penalties, and recommended actions;
- score values must be bounded 0..100;
- confidence must be `low`, `medium`, or `high`;
- an assessment without evidence links is invalid;
- a scorecard with missing dimensions is invalid;
- private rationale/detail fields must not appear in public exports;
- `reviewer_attack_surface` must be rejected if passed as a dimension;
- valid loop decisions must use complete 11-dimension scorecards. Slice O will migrate full-loop planner tests/helpers so a legacy overall-only score is no longer treated as sufficient for readiness/compile/export paths;
- overall-only construction may remain as a compatibility shape, but `ScholarlyScore.valid` must be false until the full rubric is present;
- when full dimensions exist the public summary should expose weakest dimensions;
- scorecards diagnose/prioritize repair only; tests must preserve hard-gate override behavior through existing loop/state tests.

## 5. Tests to add first

Update `tests/test_orchestra_scoring.py` before implementation:

1. rubric has exactly the 11 accepted dimensions and excludes `reviewer_attack_surface`;
2. complete scorecard with all dimensions is valid and exports public dimension details;
3. missing dimension makes score invalid with `missing_score_dimension:<name>`;
4. dimension without evidence links makes score invalid;
5. invalid confidence is rejected or marks score invalid;
6. out-of-range dimension score is rejected or marks score invalid;
7. `reviewer_attack_surface` dimension is rejected;
8. public export omits private rationale/detail;
9. compact scorecard shows overall, readiness band, weakest dimensions, blockers, and next-step hint;
10. full-loop planner tests migrate valid-score fixtures to complete 11-dimension scorecards;
11. overall-only legacy score is invalid and routes to `build_scoring_bundle`;
12. existing hard-gate override loop tests still pass.

## 6. Validation for this slice

Required before commit/push:

```bash
.venv/bin/python -m pytest tests/test_orchestra_scoring.py tests/test_orchestra_full_loop_planner.py tests/test_orchestra_state_contract.py -q
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
.venv/bin/python -m pytest tests/test_orchestra_scoring.py tests/test_orchestra_full_loop_planner.py tests/test_orchestra_state_contract.py -q
# 30 passed

.venv/bin/python -m pytest tests/test_orchestra_*.py tests/test_private_smoke_safety.py -q
# 101 passed, 8 subtests passed

.venv/bin/python -m pytest -q
# 804 passed, 113 subtests passed

scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
# status ok, scanned_file_count=190, match_count=0

git diff --check
# clean
```

Critic implementation validation: APPROVE after adding unknown-dimension invalidation and public redaction
for `to_public_dict()`, `to_summary()`, and compact scorecard output.

## 7. Explicit non-goals

Slice O must not:

- call LLM Critic/model providers;
- invent manuscript quality scores from deterministic heuristics;
- alter live pipeline behavior;
- let scores override hard gates;
- add domain/private-specific dimensions or examples;
- include `reviewer_attack_surface`.

## 8. Stop/replan triggers

Stop and replan if:

- the scorecard can pass without all dimensions;
- missing evidence links are treated as acceptable;
- private rationale appears in public export;
- hard-gate tests regress;
- implementation drifts into live model scoring instead of schema contracts.
