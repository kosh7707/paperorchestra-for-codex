from __future__ import annotations

import json
from pathlib import Path

from paperorchestra.core.session import artifact_path, set_current_session
from paperorchestra.loop_engine.ralph import repair
from paperorchestra.loop_engine.ralph import repair_issue_packet, repair_prompt, repair_recheck


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_repair_facade_reexports_issue_and_recheck_helpers() -> None:
    assert repair._claim_safety_repair_issues is repair_issue_packet._claim_safety_repair_issues
    assert repair._citation_density_repair_issues is repair_issue_packet._citation_density_repair_issues
    assert repair._citation_integrity_metrics is repair_recheck._citation_integrity_metrics
    assert repair._high_risk_issue_metrics_from_packet is repair_recheck._high_risk_issue_metrics_from_packet
    assert repair._strictly_improves is repair_recheck._strictly_improves
    assert repair._repair_prompt is repair_prompt._repair_prompt


def test_repair_facade_preserves_legacy_module_aliases() -> None:
    from paperorchestra.loop_engine.quality.source_checks import _high_risk_claim_sweep
    from paperorchestra.loop_engine.ralph.state import NON_SUPPORTED_CITATION_STATUSES
    from paperorchestra.manuscript.source_obligations import evaluate_source_obligations, source_obligations_path
    from paperorchestra.reviews.citation_integrity import build_citation_integrity_audit

    assert repair.NON_SUPPORTED_CITATION_STATUSES is NON_SUPPORTED_CITATION_STATUSES
    assert repair.evaluate_source_obligations is evaluate_source_obligations
    assert repair.source_obligations_path is source_obligations_path
    assert repair.build_citation_integrity_audit is build_citation_integrity_audit
    assert repair._high_risk_claim_sweep is _high_risk_claim_sweep


def test_claim_safety_repair_issues_reads_density_duplicate_and_high_risk_artifacts(tmp_path: Path) -> None:
    set_current_session(tmp_path, "po-test")
    _write_json(
        artifact_path(tmp_path, "citation_integrity.audit.json"),
        {
            "checks": {
                "citation_density": {
                    "bomb_sentences": [
                        {"id": "dense-1", "sentence": "Dense citation sentence.", "citation_keys": ["A", "B", "C"]}
                    ],
                    "bomb_paragraph_key_sets": [["A", "B", "C", "D"]],
                },
                "duplicate_support": {"duplicate_keys": ["A"]},
            }
        },
    )
    _write_json(
        artifact_path(tmp_path, "citation_support_review.json"),
        {
            "items": [
                {
                    "id": "support-1",
                    "sentence": "Repeated support.",
                    "citation_keys": ["A"],
                    "support_status": "supported",
                }
            ]
        },
    )
    _write_json(
        artifact_path(tmp_path, "quality-eval.json"),
        {
            "tiers": {
                "tier_2_claim_safety": {
                    "checks": {
                        "high_risk_claim_sweep": {
                            "items": [{"line": 12, "sentence": "A risky claim.", "reason": "uncited"}]
                        }
                    }
                }
            }
        },
    )

    issues = repair_issue_packet._claim_safety_repair_issues(tmp_path)

    issue_types = [item["issue_type"] for item in issues]
    assert issue_types == [
        "citation_bomb_sentence",
        "citation_bomb_paragraph",
        "citation_duplicate_support",
        "high_risk_uncited_claim",
    ]
    assert issues[2]["affected_items"][0]["id"] == "support-1"
    assert issues[3]["line"] == 12


def test_repair_recheck_metrics_summarize_packet_and_audit_payloads() -> None:
    audit_metrics = repair_recheck._citation_integrity_metrics(
        {
            "status": "fail",
            "failing_codes": ["citation_bomb_detected"],
            "checks": {
                "citation_density": {
                    "bomb_sentences": [{"id": "dense"}],
                    "bomb_paragraph_key_sets": [["A", "B"]],
                },
                "duplicate_support": {"duplicate_keys": ["A", "B"]},
            },
        }
    )
    assert audit_metrics["target_issue_count"] == 4
    assert audit_metrics["duplicate_support_count"] == 2

    packet_metrics = repair_recheck._citation_issue_metrics_from_packet(
        [
            {"issue_type": "citation_bomb_sentence"},
            {"issue_type": "citation_duplicate_support"},
        ]
    )
    assert packet_metrics["status"] == "fail"
    assert packet_metrics["failing_codes"] == ["citation_bomb_detected", "citation_duplicate_support"]

    high_risk = repair_recheck._high_risk_issue_metrics_from_packet(
        [{"issue_type": "high_risk_uncited_claim"}, {"issue_type": "other"}]
    )
    assert high_risk == {"status": "fail", "failing_codes": ["high_risk_uncited_claim"], "item_count": 1}
    assert repair_recheck._strictly_improves(2, 1) is True
    assert repair_recheck._strictly_improves(2, 2) is False
