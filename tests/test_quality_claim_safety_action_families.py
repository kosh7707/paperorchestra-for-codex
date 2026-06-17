from __future__ import annotations

from paperorchestra.loop_engine.quality.action_plan.citation_integrity import _append_citation_integrity_actions


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
