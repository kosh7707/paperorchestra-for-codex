from __future__ import annotations

from pathlib import Path

import pytest

from paperorchestra.core.errors import ContractError
from paperorchestra.runtime.providers import ProviderError, TransientProviderError
from paperorchestra.feedback import operator_candidates, operator_verification


def test_candidate_approval_source_role_requires_single_supported_source() -> None:
    assert operator_candidates._candidate_approval_source_role({"issues": []}) is None
    assert (
        operator_candidates._candidate_approval_source_role(
            {"issues": [{"source_artifact_role": "qa_loop_execution"}, {"source_artifact_role": "ignored"}]}
        )
        == "qa_loop_execution"
    )
    with pytest.raises(ContractError, match="exactly one"):
        operator_candidates._candidate_approval_source_role(
            {
                "issues": [
                    {"source_artifact_role": "qa_loop_execution"},
                    {"source_artifact_role": "operator_feedback_execution"},
                ]
            }
        )


def test_executor_failure_category_keeps_public_failure_taxonomy() -> None:
    assert operator_candidates._executor_failure_category(TransientProviderError("retry exhausted")) == "provider_transient_retry_exhausted"
    assert operator_candidates._executor_failure_category(ProviderError("provider died")) == "provider_error"
    assert operator_candidates._executor_failure_category(TimeoutError("slow")) == "timeout"
    assert operator_candidates._executor_failure_category(ContractError("latex extraction failed")) == "extraction_failed"
    assert operator_candidates._executor_failure_category(ContractError("bad state")) == "contract_error"
    assert operator_candidates._executor_failure_category(RuntimeError("boom")) == "unexpected_exception"


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
