from __future__ import annotations

from pathlib import Path

from paperorchestra.orchestra.state import HardGateStatus, OrchestraFacets, OrchestraState


def _state(tmp_path: Path, *, facets: OrchestraFacets | None = None, hard_gates: HardGateStatus | None = None, author_override: str | None = None) -> OrchestraState:
    return OrchestraState.new(
        cwd=tmp_path,
        facets=facets or OrchestraFacets(),
        hard_gates=hard_gates,
        author_override=author_override,
    )


def test_readiness_derivation_preserves_blocker_priority(tmp_path: Path) -> None:
    hard_gate = _state(
        tmp_path,
        facets=OrchestraFacets(session="no_session", material="missing"),
        hard_gates=HardGateStatus(status="fail"),
    )
    override_conflict = _state(
        tmp_path,
        facets=OrchestraFacets(claims="conflict"),
        author_override="draft anyway",
    )
    figure_block = _state(
        tmp_path,
        facets=OrchestraFacets(figures="placeholder_only", quality="near_ready"),
    )

    assert hard_gate.readiness.label == "not_ready"
    assert hard_gate.readiness.rationale == "Hard gate failures block readiness."
    assert override_conflict.readiness.rationale == "Author override conflicts with current evidence."
    assert figure_block.readiness.rationale == "Figure gate prevents final readiness."


def test_readiness_derivation_distinguishes_drafting_states(tmp_path: Path) -> None:
    notice_required = _state(
        tmp_path,
        facets=OrchestraFacets(
            material="inventoried_sufficient",
            source_digest="ready",
            claims="validated",
            evidence="supported",
            writing="not_allowed",
        ),
    )
    drafting_allowed = _state(
        tmp_path,
        facets=OrchestraFacets(material="inventoried_sufficient", writing="drafting_allowed"),
    )
    finalization = _state(
        tmp_path,
        facets=OrchestraFacets(material="inventoried_sufficient", quality="human_finalization_candidate"),
        hard_gates=HardGateStatus(status="pass"),
    )

    assert notice_required.readiness.label == "draft_blocked"
    assert drafting_allowed.readiness.label == "ready_for_drafting"
    assert drafting_allowed.readiness.status == "ready"
    assert finalization.readiness.label == "ready_for_human_finalization"
    assert finalization.readiness.status == "ready"


def test_five_axis_status_projection_maps_facets(tmp_path: Path) -> None:
    state = _state(
        tmp_path,
        facets=OrchestraFacets(
            material="inventoried_sufficient",
            source_digest="ready",
            claims="validated",
            evidence="supported",
            citations="warnings_only",
            figures="human_finalization_needed",
            writing="not_allowed",
        ),
    )

    assert state.five_axis_status == {
        "materials": "ready",
        "claims": "supported",
        "citations": "warnings",
        "figures": "human_polish",
        "readiness": "draft_blocked",
    }
