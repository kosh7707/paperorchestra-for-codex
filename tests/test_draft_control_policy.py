from __future__ import annotations

from pathlib import Path

from paperorchestra.orchestra.draft_control import (
    CitationObligationSignal,
    ClaimSignal,
    DraftControlInput,
    DraftControlPolicy,
    EvidenceObligationSignal,
)
from paperorchestra.orchestra.state import OrchestraFacets, OrchestraState


def _state(tmp_path: Path) -> OrchestraState:
    return OrchestraState.new(
        cwd=tmp_path,
        facets=OrchestraFacets(
            session="initialized",
            material="inventoried_sufficient",
            source_digest="ready",
        ),
    )


def _claim(**overrides: str) -> ClaimSignal:
    data = {
        "claim_id": "c1",
        "claim_type": "method",
        "graph_role": "support",
        "evidence_status": "supported",
    }
    data.update(overrides)
    return ClaimSignal(**data)


def _decide(tmp_path: Path, **kwargs: object):
    return DraftControlPolicy().evaluate(DraftControlInput(base_state=_state(tmp_path), **kwargs))


def test_draft_control_blocks_until_claim_graph_exists(tmp_path: Path) -> None:
    decision = _decide(tmp_path)

    assert decision.status == "blocked"
    assert decision.reasons == ["claim_graph_missing"]
    assert decision.actions[0].action_type == "build_claim_graph"
    assert decision.draft_allowed is False


def test_draft_control_blocks_until_evidence_obligation_map_exists(tmp_path: Path) -> None:
    decision = _decide(tmp_path, claims=[_claim()], evidence_obligation_map_present=False)

    assert decision.status == "blocked"
    assert decision.reasons == ["evidence_obligations_missing"]
    assert decision.actions[0].action_type == "build_evidence_obligations"


def test_draft_control_routes_critical_citation_blockers_to_research(tmp_path: Path) -> None:
    decision = _decide(
        tmp_path,
        claims=[_claim(claim_id="security", claim_type="security")],
        citation_obligations=[
            CitationObligationSignal(
                obligation_id="cite1",
                claim_id="security",
                status="unknown_reference",
                critical=True,
            )
        ],
        author_override="please draft anyway",
    )

    assert decision.status == "research_needed"
    assert decision.reasons == ["critical_unknown_reference", "author_override_cannot_bypass_critical_blocker"]
    assert decision.actions[0].action_type == "start_autoresearch"
    assert decision.actions[0].requires_omx is True


def test_draft_control_distinguishes_durable_and_machine_solvable_research_gaps(tmp_path: Path) -> None:
    durable = _decide(
        tmp_path,
        claims=[_claim()],
        evidence_obligations=[EvidenceObligationSignal("e1", "c1", "durable_research_needed")],
    )
    machine = _decide(
        tmp_path,
        claims=[_claim()],
        evidence_obligations=[EvidenceObligationSignal("e2", "c1", "missing", machine_solvable=True)],
    )

    assert durable.status == "research_needed"
    assert durable.reasons == ["durable_research_needed"]
    assert durable.actions[0].action_type == "start_autoresearch_goal"
    assert machine.status == "research_needed"
    assert machine.reasons == ["machine_solvable_evidence_gap"]
    assert machine.actions[0].action_type == "start_autoresearch"


def test_draft_control_sends_high_criticality_conflicts_to_human_needed(tmp_path: Path) -> None:
    decision = _decide(
        tmp_path,
        claims=[_claim(claim_id="c1", claim_type="security", evidence_status="conflict")],
    )

    assert decision.status == "human_needed"
    assert decision.reasons == ["high_criticality_claim_conflict"]
    assert decision.actions[0].action_type == "start_deep_interview"


def test_draft_control_auto_weakens_low_criticality_unsupported_claims(tmp_path: Path) -> None:
    decision = _decide(
        tmp_path,
        claims=[_claim(claim_type="background", graph_role="leaf", evidence_status="unknown")],
    )

    assert decision.status == "blocked"
    assert decision.reasons == ["low_criticality_unsupported_claim"]
    assert decision.actions[0].action_type == "auto_weaken_or_delete_claim"


def test_draft_control_requires_notice_before_allowing_drafting(tmp_path: Path) -> None:
    blocked = _decide(tmp_path, claims=[_claim()])
    allowed = _decide(tmp_path, claims=[_claim()], prewriting_notice_acknowledged=True)

    assert blocked.status == "blocked"
    assert blocked.reasons == ["prewriting_notice_required"]
    assert blocked.actions[0].action_type == "show_prewriting_notice"
    assert allowed.status == "draft_allowed"
    assert allowed.actions == []
    assert allowed.draft_allowed is True
    assert allowed.state.facets.writing == "drafting_allowed"
