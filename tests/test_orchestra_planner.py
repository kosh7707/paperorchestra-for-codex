from __future__ import annotations

from pathlib import Path

from paperorchestra.orchestra.planner import ActionPlanner
from paperorchestra.orchestra.state import OrchestraFacets, OrchestraState


def _state(tmp_path: Path, facets: OrchestraFacets, *, blocking_reasons: list[str] | None = None) -> OrchestraState:
    return OrchestraState.new(cwd=tmp_path, facets=facets, blocking_reasons=blocking_reasons)


def test_action_planner_qa_objective_overrides_strict_omx_block(tmp_path: Path) -> None:
    state = _state(tmp_path, OrchestraFacets(omx="required_missing"))

    action = ActionPlanner().plan(state, objective="qa", strict_omx=True)[0]

    assert action.action_type == "start_ultraqa"
    assert action.reason == "qa_objective_requested"


def test_action_planner_strict_omx_blocks_before_generic_intake(tmp_path: Path) -> None:
    state = _state(tmp_path, OrchestraFacets(omx="required_missing"))

    action = ActionPlanner().plan(state, strict_omx=True)[0]

    assert action.action_type == "block"
    assert action.reason == "missing_omx_invocation_evidence"
    assert action.requires_omx is True
    assert action.evidence_required is True
    assert action.omx_surface is None


def test_action_planner_explicit_research_gap_outranks_missing_material_defaults(tmp_path: Path) -> None:
    state = _state(tmp_path, OrchestraFacets(evidence="durable_research_needed"))

    action = ActionPlanner().plan(state)[0]

    assert action.action_type == "start_autoresearch_goal"
    assert action.reason == "durable_research_needed"


def test_action_planner_routes_ready_preconditions_to_prewriting_notice(tmp_path: Path) -> None:
    state = _state(
        tmp_path,
        OrchestraFacets(
            session="initialized",
            material="inventoried_sufficient",
            source_digest="ready",
            claims="validated",
            evidence="supported",
            writing="not_allowed",
        ),
    )

    action = ActionPlanner().plan(state)[0]

    assert action.action_type == "show_prewriting_notice"
    assert action.reason == "prewriting_notice_required"
