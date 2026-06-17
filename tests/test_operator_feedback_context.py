from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from paperorchestra.core.errors import ContractError
from paperorchestra.feedback import operator_feedback_context


def test_load_operator_feedback_context_collects_preflight_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    imported_path = tmp_path / "operator_feedback.imported.json"
    imported_path.write_text("{}", encoding="utf-8")
    imported = {
        "intent": "generate_new_operator_candidate",
        "manuscript_sha256": "sha256:paper",
        "issues": [{"owner_category": "operator"}, {"owner_category": "author"}],
    }
    packet = {"packet": True}
    base_quality_eval = {
        "failing_codes": ["active_old"],
        "tiers": {"tier_2_claim_safety": {"failing_codes": ["tier2_old"]}},
    }
    state = SimpleNamespace(artifacts=SimpleNamespace(paper_full_tex="paper.full.tex"))
    execution = {"attempts": [], "promotion_status": "candidate_ready"}

    monkeypatch.setattr(operator_feedback_context, "_load_imported_feedback", lambda path: imported)
    monkeypatch.setattr(operator_feedback_context, "_load_packet_from_imported", lambda payload: packet)
    monkeypatch.setattr(operator_feedback_context, "load_session", lambda cwd: state)
    monkeypatch.setattr(operator_feedback_context, "_file_sha256", lambda path: "sha256:paper")
    monkeypatch.setattr(operator_feedback_context, "_packet_artifact_payload", lambda pkt, role: base_quality_eval if role == "quality_eval" else None)
    monkeypatch.setattr(operator_feedback_context, "_packet_prior_operator_attempts", lambda pkt: [{"attempt_index": 0}])
    monkeypatch.setattr(operator_feedback_context, "_tier_failing_codes", lambda payload, tier: ["tier2_old"])
    monkeypatch.setattr(operator_feedback_context, "_quality_failing_codes", lambda payload: ["active_old"])
    monkeypatch.setattr(operator_feedback_context, "_build_operator_execution_record", lambda *args, **kwargs: execution)

    context = operator_feedback_context.load_operator_feedback_context(
        cwd=tmp_path,
        imported_feedback_path=imported_path,
        max_supervised_iterations=2,
    )

    assert context.imported_path == imported_path.resolve()
    assert context.imported is imported
    assert context.packet is packet
    assert context.intent == "generate_new_operator_candidate"
    assert context.state is state
    assert context.current_sha == "sha256:paper"
    assert context.base_quality_eval is base_quality_eval
    assert context.packet_prior_attempts == [{"attempt_index": 0}]
    assert context.base_tier2_failures == {"tier2_old"}
    assert context.base_active_failures == {"active_old"}
    assert context.execution is execution
    assert context.owner_categories == ["operator", "author"]


def test_load_operator_feedback_context_rejects_stale_feedback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    imported_path = tmp_path / "operator_feedback.imported.json"
    imported_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(operator_feedback_context, "_load_imported_feedback", lambda path: {"manuscript_sha256": "sha256:old"})
    monkeypatch.setattr(operator_feedback_context, "_load_packet_from_imported", lambda payload: {})
    monkeypatch.setattr(operator_feedback_context, "load_session", lambda cwd: SimpleNamespace(artifacts=SimpleNamespace(paper_full_tex="paper.full.tex")))
    monkeypatch.setattr(operator_feedback_context, "_file_sha256", lambda path: "sha256:new")

    with pytest.raises(ContractError, match="stale"):
        operator_feedback_context.load_operator_feedback_context(
            cwd=tmp_path,
            imported_feedback_path=imported_path,
            max_supervised_iterations=1,
        )


def test_operator_feedback_attempt_count_matches_intent() -> None:
    assert operator_feedback_context.operator_feedback_attempt_count(
        intent="reject_candidate_with_reason",
        max_supervised_iterations=3,
    ) == 0
    assert operator_feedback_context.operator_feedback_attempt_count(
        intent="approve_existing_candidate",
        max_supervised_iterations=3,
    ) == 1
    assert operator_feedback_context.operator_feedback_attempt_count(
        intent="generate_new_operator_candidate",
        max_supervised_iterations=3,
    ) == 3
