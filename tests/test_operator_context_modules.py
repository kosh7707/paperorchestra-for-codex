from __future__ import annotations

import json
from pathlib import Path

from paperorchestra.feedback import operator_context
from paperorchestra.feedback.operator_contract import OPERATOR_PACKET_SCHEMA_VERSION
from paperorchestra.feedback.packet_artifacts import _file_sha256, _packet_sha256


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _artifact(role: str, path: Path) -> dict[str, str]:
    digest = _file_sha256(path)
    assert digest
    return {"role": role, "path": str(path), "sha256": digest}


def _operator_packet(tmp_path: Path) -> Path:
    citation_review = _write_json(
        tmp_path / "citation-review.json",
        {
            "items": [
                {
                    "id": "weak-1",
                    "support_status": "weakly_supported",
                    "sentence": "Weak citation sentence.",
                    "citation_keys": ["A"],
                    "suggested_fix": "Ground or soften the claim.",
                },
                {
                    "id": "supported-1",
                    "support_status": "supported",
                    "sentence": "Already supported sentence.",
                    "citation_keys": ["D"],
                },
            ]
        },
    )
    quality_eval = _write_json(
        tmp_path / "quality-eval.json",
        {
            "tiers": {
                "tier_2_claim_safety": {
                    "failing_codes": ["high_risk_uncited_claim"],
                    "checks": {
                        "high_risk_claim_sweep": {
                            "items": [{"line": 7, "sentence": "A high-risk claim.", "reason": "uncited"}]
                        }
                    },
                }
            }
        },
    )
    citation_integrity = _write_json(
        tmp_path / "citation-integrity.json",
        {
            "failing_codes": ["citation_duplicate_support"],
            "checks": {
                "duplicate_support": {"duplicate_keys": ["A"]},
                "citation_density": {
                    "bomb_sentences": [
                        {"id": "dense-1", "sentence": "Too many citations.", "citation_keys": ["A", "B", "C"]}
                    ]
                },
            },
        },
    )
    figure_review = _write_json(
        tmp_path / "figure-review.json",
        {
            "figures": [
                {
                    "label": "fig:pipeline",
                    "section_title": "Method",
                    "failing_codes": ["figure_unreferenced"],
                    "caption": "A weak caption.",
                    "included_assets": ["pipeline.pdf"],
                }
            ]
        },
    )
    packet = {
        "schema_version": OPERATOR_PACKET_SCHEMA_VERSION,
        "session_id": "po-test",
        "manuscript_sha256": "0" * 64,
        "artifacts": [
            _artifact("citation_support_review", citation_review),
            _artifact("quality_eval", quality_eval),
            _artifact("citation_integrity_audit", citation_integrity),
            _artifact("figure_placement_review", figure_review),
        ],
    }
    packet["packet_sha256"] = _packet_sha256(packet)
    return _write_json(tmp_path / "packet.json", packet)


def test_operator_issue_context_reads_packet_artifacts_without_name_errors(tmp_path: Path) -> None:
    packet_path = _operator_packet(tmp_path)

    context = operator_context._operator_issue_context({"packet_path": str(packet_path)})

    assert context["problematic_citation_items"][0]["id"] == "weak-1"
    assert context["high_risk_uncited_claims"][0]["line"] == 7
    assert context["citation_density_issues"][0]["id"] == "dense-1"
    assert context["citation_duplicate_support_issues"][0]["citation_key"] == "A"
    assert context["figure_placement_issues"][0]["label"] == "fig:pipeline"
    assert context["refinement_constraints"]["forbidden_new_tier2_codes"]
    assert context["protected_supported_citation_items"][0]["id"] == "supported-1"
