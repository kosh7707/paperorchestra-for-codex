from __future__ import annotations

from paperorchestra.orchestra.policies import InteractionPolicy, ReadinessPolicy, StateValidator
from paperorchestra.orchestra.state import HardGateStatus, OrchestraFacets, OrchestraState, ReadinessSummary


def _state(tmp_path, *, facets: OrchestraFacets | None = None, hard_gates: HardGateStatus | None = None, author_override: str | None = None) -> OrchestraState:
    return OrchestraState.new(
        cwd=tmp_path,
        facets=facets or OrchestraFacets(),
        hard_gates=hard_gates,
        author_override=author_override,
    )


def test_readiness_policy_adds_blocking_reasons_without_mutating_input(tmp_path) -> None:
    state = _state(
        tmp_path,
        facets=OrchestraFacets(claims="conflict", omx="required_missing", figures="placeholder_only"),
        hard_gates=HardGateStatus(status="fail", failures=["compile_failed"]),
        author_override="draft anyway",
    )

    updated = ReadinessPolicy().apply(state)

    assert updated is not state
    assert state.blocking_reasons == []
    assert updated.blocking_reasons == [
        "compile_failed",
        "author_override_conflicts_with_evidence",
        "missing_omx_invocation_evidence",
        "placeholder_figure_unresolved",
    ]
    assert updated.readiness.label == "not_ready"


def test_state_validator_reports_inconsistent_ready_and_drafting_states(tmp_path) -> None:
    state = _state(
        tmp_path,
        facets=OrchestraFacets(
            material="missing",
            source_digest="missing",
            claims="conflict",
            evidence="research_needed",
            citations="unsupported_critical",
            writing="drafting_allowed",
            quality="human_finalization_candidate",
            interaction="human_needed",
            omx="required_missing",
        ),
        hard_gates=HardGateStatus(status="fail"),
        author_override="force it",
    )
    state.readiness = ReadinessSummary("ready_for_human_finalization", "ready", "forced")

    result = StateValidator().validate(state)

    assert result.valid is False
    assert result.issues == [
        "hard_gate_failure_cannot_be_ready",
        "score_cannot_override_hard_gate",
        "drafting_allowed_without_ready_preconditions",
        "machine_solvable_gap_misrouted_to_human_needed",
        "strict_omx_missing_evidence_cannot_be_ready",
        "critical_citation_problem_cannot_be_ready",
        "author_override_conflicts_with_evidence",
    ]


def test_interaction_policy_classifies_machine_and_human_gaps() -> None:
    policy = InteractionPolicy()

    assert policy.classify_gap(gap_type="citation") == "research_needed"
    assert policy.classify_gap(gap_type="source", criticality="durable") == "durable_research_needed"
    assert policy.classify_gap(gap_type="claim_strategy") == "human_needed"
    assert policy.classify_gap(gap_type="unknown") == "research_needed"
