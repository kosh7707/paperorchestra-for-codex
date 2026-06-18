from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from paperorchestra.core.errors import ContractError
from paperorchestra.feedback.operator_candidate_approval import _candidate_approval_source_role, _ready_candidate_from_packet
from paperorchestra.feedback.operator_candidate_generation import _executor_failure_category
from paperorchestra.feedback.packet_bindings import _execution_payload_sha256
from paperorchestra.runtime.provider_base import ProviderError, TransientProviderError
from paperorchestra.feedback import operator_verification


def test_candidate_approval_source_role_requires_single_supported_source() -> None:
    assert _candidate_approval_source_role({"issues": []}) is None
    assert (
        _candidate_approval_source_role(
            {"issues": [{"source_artifact_role": "qa_loop_execution"}, {"source_artifact_role": "ignored"}]}
        )
        == "qa_loop_execution"
    )
    with pytest.raises(ContractError, match="exactly one"):
        _candidate_approval_source_role(
            {
                "issues": [
                    {"source_artifact_role": "qa_loop_execution"},
                    {"source_artifact_role": "operator_feedback_execution"},
                ]
            }
        )


def test_ready_candidate_from_packet_verifies_candidate_and_source_hashes(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.tex"
    candidate.write_text("approved draft", encoding="utf-8")
    execution_path = tmp_path / "qa-loop.execution.json"
    base_sha = "b" * 64
    candidate_sha = "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest()
    execution = {
        "candidate_approval": {
            "status": "human_needed_candidate_ready",
            "candidate_path": str(candidate),
            "candidate_sha256": candidate_sha,
            "base_manuscript_sha256": "sha256:" + base_sha,
            "source_execution_path": str(execution_path),
            "source_execution_sha256": "pending",
            "created_at": "2026-01-01T00:00:00Z",
        },
        "candidate_progress": {
            "forward_progress": True,
            "before_failing_codes": ["citation_missing"],
            "after_failing_codes": [],
            "citation_issue_delta": 0,
        },
        "candidate_state": {"verification": {"ok": True}},
    }
    execution["candidate_approval"]["source_execution_sha256"] = _execution_payload_sha256(execution)
    execution_path.write_text(json.dumps(execution), encoding="utf-8")
    packet = {"artifacts": [{"role": "qa_loop_execution", "path": str(execution_path)}]}

    ready = _ready_candidate_from_packet(packet, base_sha, source_artifact_role="qa_loop_execution")

    assert ready["candidate_path"] == str(candidate.resolve())
    assert ready["candidate_sha256"] == candidate_sha
    assert ready["executor_source_role"] == "qa_loop_execution"
    execution["candidate_approval"]["source_execution_sha256"] = "sha256:" + "0" * 64
    execution_path.write_text(json.dumps(execution), encoding="utf-8")
    with pytest.raises(ContractError, match="source execution hash mismatch"):
        _ready_candidate_from_packet(packet, base_sha, source_artifact_role="qa_loop_execution")


def test_executor_failure_category_keeps_public_failure_taxonomy() -> None:
    assert _executor_failure_category(TransientProviderError("retry exhausted")) == "provider_transient_retry_exhausted"
    assert _executor_failure_category(ProviderError("provider died")) == "provider_error"
    assert _executor_failure_category(TimeoutError("slow")) == "timeout"
    assert _executor_failure_category(ContractError("latex extraction failed")) == "extraction_failed"
    assert _executor_failure_category(ContractError("bad state")) == "contract_error"
    assert _executor_failure_category(RuntimeError("boom")) == "unexpected_exception"


def test_verification_block_projects_nested_quality_evidence(tmp_path: Path) -> None:
    critic_path = tmp_path / "citation-integrity-critic.json"
    critic_path.write_text(
        '{"status":"fail","manuscript_sha256":"sha256:paper","failing_codes":["citation_missing"]}',
        encoding="utf-8",
    )
    verification = {
        "validation_path": tmp_path / "validation.json",
        "validation_payload": {"ok": False},
        "compile_payload": {"ok": True, "pdf": "paper.pdf"},
        "section_path": tmp_path / "section.json",
        "figure_path": tmp_path / "figure.json",
        "figure_payload": {"manuscript_sha256": "sha256:paper"},
        "citation_path": tmp_path / "citation.json",
        "review_path": tmp_path / "review.json",
        "quality_path": tmp_path / "quality.json",
        "quality_eval": {
            "source_artifacts": {
                "citation_review_sha256": "sha256:citation",
                "citation_integrity_critic": str(critic_path),
                "citation_integrity_critic_sha256": "sha256:critic",
            },
            "tiers": {
                "tier_2_claim_safety": {
                    "checks": {
                        "citation_support_critic": {
                            "canonical_summary": "citation critic summary",
                            "citation_review_sha256": "sha256:check-citation",
                        }
                    }
                }
            },
        },
        "plan_path": tmp_path / "qa-loop.plan.json",
        "plan": {"verdict": "human_needed"},
    }

    block = operator_verification._verification_block(verification)

    assert block["validate_current"] == {"path": str(tmp_path / "validation.json"), "ok": False}
    assert block["figure_placement_review"]["manuscript_sha256"] == "sha256:paper"
    assert block["citation_support_review"] == {
        "path": str(tmp_path / "citation.json"),
        "sha256": "sha256:citation",
        "summary": "citation critic summary",
    }
    assert block["citation_integrity_critic"] == {
        "path": str(critic_path),
        "sha256": "sha256:critic",
        "status": "fail",
        "manuscript_sha256": "sha256:paper",
        "failing_codes": ["citation_missing"],
    }
    assert block["qa_loop_plan"] == {"path": str(tmp_path / "qa-loop.plan.json"), "verdict": "human_needed"}
