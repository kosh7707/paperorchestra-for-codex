from __future__ import annotations

import hashlib
from pathlib import Path

from paperorchestra.feedback import operator_human_review
from paperorchestra.feedback.packet_bindings import _execution_payload_sha256


def test_best_human_review_candidate_attempt_requires_safe_forward_progress(tmp_path: Path) -> None:
    weaker_candidate = tmp_path / "weaker.tex"
    stronger_candidate = tmp_path / "stronger.tex"
    weaker_candidate.write_text("weaker", encoding="utf-8")
    stronger_candidate.write_text("stronger", encoding="utf-8")

    best = operator_human_review._best_human_review_candidate_attempt(
        [
            {"attempt_index": 1, "resolved_active_failures": ["a"], "candidate_path": str(weaker_candidate)},
            {
                "attempt_index": 2,
                "resolved_active_failures": ["a", "b"],
                "candidate_path": str(stronger_candidate),
                "new_tier2_failures": ["citation_support_manual_check"],
            },
            {
                "attempt_index": 3,
                "resolved_active_failures": ["a", "b", "c"],
                "candidate_path": str(stronger_candidate),
                "new_tier2_failures": ["citation_support_unsupported"],
            },
            {
                "attempt_index": 4,
                "resolved_active_failures": ["a", "b", "c"],
                "candidate_path": str(stronger_candidate),
                "gate_reasons": ["compile_failed"],
            },
        ]
    )

    assert best is not None
    assert best["attempt_index"] == 2


def test_attach_candidate_approval_from_attempt_records_hash_bound_progress(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.tex"
    candidate.write_text("candidate paper", encoding="utf-8")
    execution_path = tmp_path / "operator_feedback.execution.json"
    execution = {"manuscript_sha256_before": "a" * 64}

    operator_human_review._attach_candidate_approval_from_attempt(
        execution,
        {
            "candidate_path": str(candidate),
            "base_active_failures": ["citation_support_unsupported"],
            "candidate_active_failures": ["citation_support_manual_check"],
            "resolved_active_failures": ["citation_support_unsupported"],
            "active_tier2_metric_delta": {"base_total": 5, "candidate_total": 2},
            "verification": {
                "quality_eval": {"path": "quality-eval.json"},
                "qa_loop_plan": {"path": "qa-plan.json", "verdict": "human_needed"},
                "citation_support_review": {"summary": {"needs_manual_check": 2}},
            },
        },
        execution_path=execution_path,
    )

    candidate_hash = hashlib.sha256(candidate.read_bytes()).hexdigest()
    assert execution["candidate_approval"]["candidate_sha256"] == f"sha256:{candidate_hash}"
    assert execution["candidate_approval"]["base_manuscript_sha256"] == "sha256:" + "a" * 64
    assert execution["candidate_approval"]["source_execution_sha256"] == _execution_payload_sha256(execution)
    assert execution["candidate_progress"]["resolved_codes"] == ["citation_support_unsupported"]
    assert execution["candidate_progress"]["citation_issue_delta"] == -3
    assert execution["candidate_state"]["qa_loop_plan_verdict"] == "human_needed"
