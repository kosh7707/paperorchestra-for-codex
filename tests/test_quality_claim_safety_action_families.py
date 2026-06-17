from __future__ import annotations

from paperorchestra.loop_engine.quality.action_plan.citation_integrity import _append_citation_integrity_actions
from paperorchestra.loop_engine.quality.action_plan.citation_quality import _append_citation_quality_actions
from paperorchestra.loop_engine.quality.action_plan.figure_grounding import _append_figure_grounding_actions
from paperorchestra.loop_engine.quality.action_plan.source_material import (
    _append_source_material_fidelity_actions,
    _append_source_obligation_actions,
)


def test_citation_integrity_actions_emit_refresh_for_missing_or_stale_artifacts() -> None:
    actions: list[dict] = []

    _append_citation_integrity_actions(
        actions,
        {
            "failing_codes": ["citation_integrity_missing"],
            "citation_integrity_audit": {"path": "integrity.json"},
        },
    )

    assert [action["code"] for action in actions] == ["citation_integrity_missing"]
    assert actions[0]["id"] == "quality-eval:citation-integrity-refresh"
    assert actions[0]["automation"] == "automatic"
    assert actions[0]["source"] == "integrity.json"


def test_citation_integrity_actions_emit_density_repair_for_policy_failures() -> None:
    actions: list[dict] = []

    _append_citation_integrity_actions(
        actions,
        {
            "failing_codes": ["citation_bomb_detected", "citation_integrity_failed"],
            "citation_integrity_audit": {"path": "integrity.json"},
        },
    )

    assert [action["code"] for action in actions] == ["citation_density_policy_failed"]
    assert actions[0]["id"] == "quality-eval:citation-density"
    assert actions[0]["automation"] == "semi_auto"
    assert actions[0]["approval_required_from"] == "citation_integrity_critic"


def test_citation_quality_actions_emit_refresh_and_critical_repair() -> None:
    actions: list[dict] = []

    _append_citation_quality_actions(
        actions,
        {"hard_gate_failures": ["citation_quality_stale", "critical_unknown_reference"]},
    )

    assert [action["code"] for action in actions] == ["citation_quality_stale", "critical_unknown_reference"]
    assert actions[0]["id"] == "quality-eval:citation-quality:citation_quality_stale"
    assert actions[0]["automation"] == "automatic"
    assert actions[1]["automation"] == "semi_auto"
    assert actions[1]["approval_required_from"] == "citation_quality_gate"


def test_figure_grounding_actions_emit_human_needed_with_context() -> None:
    actions: list[dict] = []

    _append_figure_grounding_actions(
        actions,
        {
            "path": "figure-review.json",
            "figures": [
                {
                    "label": "Figure 2",
                    "section_title": "Evaluation",
                    "included_assets": ["precision.pdf"],
                    "nearby_reference_context": "Figure 2 summarizes the full OWASP trend.",
                    "plot_manifest_match": {"purpose": "show precision trend"},
                    "failing_codes": ["figure_caption_unsupported"],
                }
            ],
        },
    )

    assert [action["code"] for action in actions] == ["figure_caption_unsupported"]
    assert actions[0]["id"] == "quality-eval:figure-grounding:figure_caption_unsupported:1"
    assert actions[0]["source"] == "figure-review.json"
    assert actions[0]["target"] == "Figure 2 in Evaluation"
    assert actions[0]["automation"] == "human_needed"
    assert "Assets: precision.pdf." in actions[0]["reason"]
    assert actions[0]["approval_required_from"] == "figure_placement_review_critic"


def test_source_material_fidelity_actions_emit_semiautomatic_repair() -> None:
    actions: list[dict] = []

    _append_source_material_fidelity_actions(actions, {"status": "fail"})

    assert [action["code"] for action in actions] == ["source_material_coverage_insufficient"]
    assert actions[0]["id"] == "quality-eval:source-material-fidelity"
    assert actions[0]["automation"] == "semi_auto"
    assert actions[0]["approval_required_from"] == "source_material_critic"


def test_source_obligation_actions_emit_refresh_and_satisfaction_repair() -> None:
    actions: list[dict] = []

    _append_source_obligation_actions(
        actions,
        {
            "path": "source-obligations.json",
            "failing_codes": ["source_obligations_stale", "source_obligation_missing"],
        },
    )

    assert [action["code"] for action in actions] == ["source_obligations_stale", "source_material_coverage_insufficient"]
    assert actions[0]["id"] == "quality-eval:source_obligations_stale"
    assert actions[0]["automation"] == "automatic"
    assert actions[0]["source"] == "source-obligations.json"
    assert actions[1]["id"] == "quality-eval:source-obligation-satisfaction"
    assert actions[1]["automation"] == "semi_auto"
    assert actions[1]["approval_required_from"] == "source_material_critic"
