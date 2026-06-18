from __future__ import annotations

from paperorchestra.orchestra.consensus import CriticConsensus, CriticVerdict
from paperorchestra.orchestra.scoring import ScholarlyScore, ScoreDimensionAssessment, ScoringBundleBuilder
from paperorchestra.orchestra.scoring_schema import SCORE_DIMENSIONS
from paperorchestra.orchestra.state import HardGateStatus, OrchestraState
from paperorchestra.orchestra.verifier_items import build_verifier_items


def _status_by_id(items):
    return {item.id: item.status for item in items}


def _reason_by_id(items):
    return {item.id: item.reason for item in items}


def _valid_score() -> ScholarlyScore:
    dimensions = {
        dimension: ScoreDimensionAssessment(score=80, confidence="medium", rationale="sufficient evidence", evidence_links=[f"artifact://{dimension}"])
        for dimension in SCORE_DIMENSIONS
    }
    return ScholarlyScore(overall=80, readiness_band="near_ready", evidence_links=["artifact://score"], dimensions=dimensions)


def test_build_verifier_items_passes_when_all_contracts_are_met(tmp_path) -> None:
    state = OrchestraState.new(cwd=tmp_path, hard_gates=HardGateStatus(status="pass"))
    bundle = ScoringBundleBuilder().build(
        phase="final",
        manuscript_sha256="a" * 64,
        required_artifacts={"paper": "artifacts/paper.tex"},
        compressed_evidence={"summary": "ok"},
    )
    consensus = CriticConsensus(
        status="pass",
        readiness_band="near_ready",
        verdicts=[
            CriticVerdict("critic-a", "near_ready", ["artifact://a"]),
            CriticVerdict("critic-b", "near_ready", ["artifact://b"]),
        ],
    )

    statuses = _status_by_id(
        build_verifier_items(state, bundle, _valid_score(), consensus, compiled=True, exported=True, unsafe_reasons=[])
    )

    assert statuses == {
        "scoring_bundle_complete": "pass",
        "score_valid_and_evidence_linked": "pass",
        "critic_consensus_two_or_more": "pass",
        "critic_consensus_near_ready_or_better": "pass",
        "hard_gates_no_fail": "pass",
        "compile_export_accounted_for": "pass",
        "public_safety_no_raw_private_evidence": "pass",
    }


def test_build_verifier_items_fail_closes_on_invalid_score_consensus_and_unsafe_refs(tmp_path) -> None:
    state = OrchestraState.new(cwd=tmp_path, hard_gates=HardGateStatus(status="fail"))
    invalid_score = ScholarlyScore(overall=101, readiness_band="ready", evidence_links=["artifact://score"], dimensions={})
    consensus = CriticConsensus(status="failed", verdicts=[CriticVerdict("critic-a", "ready", [])])

    items = build_verifier_items(
        state,
        scoring_bundle=None,
        score=invalid_score,
        consensus=consensus,
        compiled=True,
        exported=True,
        unsafe_reasons=["private_path"],
    )

    statuses = _status_by_id(items)
    reasons = _reason_by_id(items)
    assert statuses["scoring_bundle_complete"] == "blocked"
    assert statuses["score_valid_and_evidence_linked"] == "fail"
    assert reasons["score_valid_and_evidence_linked"] == "score_invalid_fail_closed"
    assert statuses["critic_consensus_two_or_more"] == "fail"
    assert statuses["hard_gates_no_fail"] == "fail"
    assert statuses["compile_export_accounted_for"] == "fail"
    assert statuses["public_safety_no_raw_private_evidence"] == "fail"
