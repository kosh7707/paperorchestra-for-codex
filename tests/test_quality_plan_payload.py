from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from paperorchestra.loop_engine.quality.plan_payload import QualityLoopPlanPayloadInput, build_quality_loop_plan_payload
from paperorchestra.loop_engine.quality.plan_sources import CitationReviewIdentity


@dataclass
class _Artifacts:
    paper_full_tex: str = "paper.tex"
    compiled_pdf: str = "paper.pdf"
    latest_reproducibility_json: str = "repro.json"
    latest_fidelity_json: str = "fidelity.json"
    latest_figure_placement_review_json: str = "figures.json"
    latest_validation_json: str = "validation.json"
    latest_section_review_json: str = "sections.json"
    narrative_plan_json: str = "narrative.json"
    claim_map_json: str = "claims.json"
    citation_placement_plan_json: str = "placements.json"


@dataclass
class _State:
    session_id: str = "session-1"
    artifacts: _Artifacts = field(default_factory=_Artifacts)


def test_quality_loop_plan_payload_builds_summary_sources_and_supervised_handoff(tmp_path: Path) -> None:
    operator_packet = tmp_path / "operator_review_packet.json"
    action_auto = {"code": "review_score_missing", "automation": "automatic"}
    action_human = {"code": "citation_needs_human", "automation": "human_needed"}
    quality_eval = {
        "schema_version": "quality-eval/1",
        "mode": "ralph",
        "manuscript_hash": "sha256:paper",
        "provenance_trust": {"level": "mixed", "mixed_acceptance": {"status": "pass"}},
        "tiers": {"tier_4_human_finalization": {"outstanding_owners": ["author"]}},
        "source_artifacts": {"citation_review_sha256": "old"},
    }
    quality_eval_for_plan = {
        **quality_eval,
        "source_artifacts": {"citation_review_sha256": "old", "citation_review_current_sha256": "new", "citation_review_identity_status": "stale_or_divergent"},
    }

    payload = build_quality_loop_plan_payload(
        QualityLoopPlanPayloadInput(
            cwd=tmp_path,
            state=_State(),
            reproducibility={"verdict": "warn", "blocking_reasons": ["block"], "warning_reasons": ["warn"]},
            fidelity={"overall_status": "pass"},
            quality_eval=quality_eval,
            quality_eval_for_plan=quality_eval_for_plan,
            quality_eval_path=tmp_path / "quality-eval.json",
            actions=[action_auto, action_human],
            verdict="human_needed",
            verdict_rationale="manual citation decision required",
            provenance_for_plan=quality_eval_for_plan["provenance_trust"],
            citation_support_review_path=tmp_path / "citation-support.json",
            citation_review_identity=CitationReviewIdentity("old", "new", "stale_or_divergent"),
            operator_packet_path=operator_packet,
            operator_packet_sha="packet-sha",
            source_obligations_path=tmp_path / "source-obligations.json",
        )
    )

    assert payload["summary"] == {
        "action_count": 2,
        "automatic_count": 1,
        "semi_auto_count": 0,
        "human_needed_count": 1,
        "manual_count": 1,
        "reproducibility_verdict": "warn",
        "fidelity_status": "pass",
    }
    assert payload["source_artifacts"]["paper_full_tex"] == "paper.tex"
    assert payload["source_artifacts"]["citation_review_sha256"] == "old"
    assert payload["source_artifacts"]["citation_review_current_sha256"] == "new"
    assert payload["source_artifacts"]["operator_review_packet"] == str(operator_packet)
    assert payload["source_artifacts"]["source_obligations"] == str(tmp_path / "source-obligations.json")
    assert payload["mixed_provenance_acceptance"] == {"status": "pass"}
    assert payload["human_handoff"]["human_action_codes"] == ["citation_needs_human"]
    assert payload["supervised_handoff"]["operator_feedback_entry"]["packet_sha256"] == "packet-sha"
    assert payload["supervised_handoff"]["actionable_failure_summary"]["owner_categories"] == ["bibliography"]
    assert payload["repair_actions"] == [action_auto, action_human]


def test_quality_loop_plan_payload_omits_supervised_handoff_when_not_human_needed(tmp_path: Path) -> None:
    payload = build_quality_loop_plan_payload(
        QualityLoopPlanPayloadInput(
            cwd=tmp_path,
            state=_State(),
            reproducibility={},
            fidelity={},
            quality_eval={"source_artifacts": {}},
            quality_eval_for_plan={"source_artifacts": {}},
            quality_eval_path=None,
            actions=[],
            verdict="continue",
            verdict_rationale="automatic actions remain",
            provenance_for_plan={},
            citation_support_review_path=tmp_path / "citation-support.json",
            citation_review_identity=CitationReviewIdentity(None, None, "missing"),
            operator_packet_path=tmp_path / "operator_review_packet.json",
            operator_packet_sha=None,
            source_obligations_path=tmp_path / "source-obligations.json",
        )
    )

    assert "supervised_handoff" not in payload
    assert payload["human_handoff"] is None
    assert payload["summary"]["action_count"] == 0


def test_quality_loop_plan_payload_owner_categories_cover_moved_mapping(tmp_path: Path) -> None:
    actions = [
        {"code": "proof_gap", "automation": "human_needed"},
        {"code": "security_claim", "automation": "human_needed"},
        {"code": "benchmark_missing", "automation": "human_needed"},
        {"code": "compile_failed", "automation": "human_needed"},
        {"code": "author_judgment", "automation": "human_needed"},
    ]

    payload = build_quality_loop_plan_payload(
        QualityLoopPlanPayloadInput(
            cwd=tmp_path,
            state=_State(),
            reproducibility={},
            fidelity={},
            quality_eval={"source_artifacts": {}},
            quality_eval_for_plan={"source_artifacts": {}},
            quality_eval_path=None,
            actions=actions,
            verdict="human_needed",
            verdict_rationale="manual categories",
            provenance_for_plan={},
            citation_support_review_path=tmp_path / "citation-support.json",
            citation_review_identity=CitationReviewIdentity(None, None, "missing"),
            operator_packet_path=tmp_path / "operator_review_packet.json",
            operator_packet_sha=None,
            source_obligations_path=tmp_path / "source-obligations.json",
        )
    )

    assert payload["supervised_handoff"]["actionable_failure_summary"]["owner_categories"] == [
        "author",
        "experiment",
        "implementation",
        "proof",
    ]
