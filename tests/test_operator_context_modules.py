from __future__ import annotations

import json
from pathlib import Path

from paperorchestra.feedback import operator_context
from paperorchestra.feedback.operator_contract import OPERATOR_PACKET_SCHEMA_VERSION
from paperorchestra.feedback.operator_contexts import citation_issues
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


def test_citation_issue_context_projects_problematic_items_and_limits_examples() -> None:
    problematic = citation_issues._problematic_citation_context(
        {
            "items": [
                {"id": "ok", "support_status": "supported", "sentence": "ok"},
                {"id": "weak", "support_status": "weakly_supported", "citation_keys": ["A"], "sentence": "weak"},
                {"id": "manual", "status": "manual_check", "citation_keys": ["B"], "sentence": "manual"},
            ]
        },
        limit=1,
    )

    assert problematic == [
        {
            "id": "weak",
            "support_status": "weakly_supported",
            "claim_type": None,
            "risk": None,
            "sentence": "weak",
            "citation_keys": ["A"],
            "suggested_fix": "",
            "model_reasoning": "",
        }
    ]


def test_duplicate_and_density_contexts_preserve_ordering_and_caps() -> None:
    duplicate = citation_issues._duplicate_support_context(
        {"checks": {"duplicate_support": {"duplicate_keys": ["A"]}}},
        {
            "items": [
                {"id": "one", "citation_keys": ["A"], "sentence": "one"},
                {"id": "two", "citation_keys": ["A"], "sentence": "two"},
            ]
        },
        examples_per_key=1,
    )
    density = citation_issues._citation_density_context(
        {
            "checks": {
                "citation_density": {
                    "bomb_sentences": [{"id": "s", "sentence": "sentence", "citation_keys": ["A"]}],
                    "bomb_paragraph_key_sets": [["B", "C"]],
                }
            }
        }
    )

    assert duplicate[0]["occurrence_count"] == 2
    assert duplicate[0]["affected_items"] == [
        {"id": "one", "support_status": "unknown", "claim_type": None, "risk": None, "sentence": "one"}
    ]
    assert [item["issue_type"] for item in density] == ["citation_bomb_sentence", "citation_bomb_paragraph"]


def test_protected_citation_target_context_collects_problematic_review_and_integrity_targets() -> None:
    from paperorchestra.feedback.operator_contexts.citation_protection_target_context import (
        _protected_citation_target_context,
    )

    targets = _protected_citation_target_context(
        {
            "items": [
                {"id": "weak-item", "support_status": "weak", "sentence": "Weak sentence."},
                {"id": "supported-item", "support_status": "supported", "sentence": "Supported sentence."},
            ],
            "cases": [
                {"id": "bad-case", "verdict": "fail", "anchor": "Failed anchor."},
                {"id": "good-case", "verdict": "pass", "anchor": "Good anchor."},
            ],
        },
        {
            "checks": {
                "duplicate_support": {"duplicate_keys": ["DupKey"]},
                "citation_density": {
                    "bomb_sentences": [{"sentence": "Dense sentence.", "citation_keys": ["DenseA", "DenseB"]}],
                    "bomb_paragraph_key_sets": [["ParaA", "ParaB"]],
                },
            }
        },
    )

    assert targets["ids"] == {"weak-item", "bad-case"}
    assert targets["texts"] == {"Weak sentence.", "Failed anchor.", "Dense sentence."}
    assert targets["key_exclusions"] == {"DupKey", "DenseA", "DenseB", "ParaA", "ParaB"}


def test_protected_supported_citation_context_excludes_active_targets_and_caps() -> None:
    from paperorchestra.feedback.operator_contexts.citation_protection_supported import (
        _protected_item_text,
        _protected_supported_citation_context,
    )

    protected = _protected_supported_citation_context(
        {
            "items": [
                {"id": "bad-id", "support_status": "weak", "sentence": "Bad id target.", "citation_keys": ["SafeA"]},
                {"id": "bad-id", "support_status": "supported", "sentence": "Bad id sentence.", "citation_keys": ["SafeA"]},
                {"id": "bad-text", "support_status": "supported", "sentence": "Bad text sentence.", "citation_keys": ["SafeB"]},
                {"id": "bad-key", "support_status": "supported", "sentence": "Bad key sentence.", "citation_keys": ["DupKey"]},
                {"id": "safe-item", "support_status": "supported", "sentence": "Safe supported sentence.", "citation_keys": ["SafeC"]},
                {"id": "unsupported", "support_status": "unsupported", "sentence": "Unsupported sentence.", "citation_keys": ["SafeD"]},
            ],
            "cases": [
                {"id": "safe-case", "verdict": "pass", "anchor": "Safe supported anchor.", "key": "SafeCase"},
            ],
        },
        {
            "checks": {
                "duplicate_support": {"duplicate_keys": ["DupKey"]},
                "citation_density": {"bomb_sentences": [{"sentence": "Bad text sentence.", "citation_keys": []}]},
            }
        },
        limit=2,
    )

    assert protected == [
        {
            "id": "safe-item",
            "citation_keys": ["SafeC"],
            "sentence": "Safe supported sentence.",
            "source_shape": "items",
            "required_action": "preserve this already-supported citation-bearing sentence unless an active issue explicitly targets it",
        },
        {
            "id": "safe-case",
            "citation_keys": ["SafeCase"],
            "anchor": "Safe supported anchor.",
            "source_shape": "cases",
            "required_action": "preserve this already-supported citation-bearing anchor unless an active issue explicitly targets it",
        },
    ]
    assert _protected_item_text(protected[0]) == "Safe supported sentence."
    assert _protected_item_text(protected[1]) == "Safe supported anchor."
