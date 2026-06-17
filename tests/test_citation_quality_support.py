from __future__ import annotations

from pathlib import Path

from paperorchestra.reviews import citation_quality
from paperorchestra.reviews import citation_quality_support as support


def test_citation_quality_support_facade_exports_adapter_helpers() -> None:
    assert citation_quality._support_items is support._support_items
    assert citation_quality._support_groups_for_quality_items is support._support_groups_for_quality_items
    assert citation_quality._worst_support_status is support._worst_support_status
    assert citation_quality._public_failure_code is support._public_failure_code


def test_v3_support_review_cases_become_quality_items(tmp_path: Path) -> None:
    evidence_path = tmp_path / "evidence.txt"
    evidence_path.write_text("supporting passage", encoding="utf-8")

    payload = {
        "schema": "citation-support-review/3",
        "cases": [
            {"id": "c1", "key": "KeyA", "verdict": "pass", "evidence": {"status": "text", "path": "evidence.txt"}},
            {"id": "c2", "key": "KeyB", "verdict": "pass", "evidence": {"status": "text", "path": "missing.txt"}},
            {"id": "c3", "key": "KeyC", "verdict": "weak", "evidence": {"status": "metadata"}},
            {"id": "c4", "key": "KeyD", "verdict": "human_needed", "evidence": {"status": "blocked"}},
        ],
    }

    items = support._support_items(payload, run_root=tmp_path)

    assert [item["support_status"] for item in items] == [
        "supported",
        "insufficient_evidence",
        "metadata_only",
        "insufficient_evidence",
    ]
    assert items[0] == {
        "id": "c1",
        "case_id": "c1",
        "citation_keys": ["KeyA"],
        "support_status": "supported",
        "evidence_status": "text",
        "evidence_readable": True,
        "review_schema": "citation-support-review/3",
        "verdict": "pass",
    }
    assert support._public_failure_code([items[-1]], ["critical_unsupported_citation"]) == "human_needed"


def test_quality_support_groups_v3_cases_separately_from_legacy_items() -> None:
    v3_a = {"id": "v3-a", "citation_keys": ["A"], "review_schema": "citation-support-review/3"}
    v3_b = {"id": "v3-b", "citation_keys": ["A"], "review_schema": "citation-support-review/3"}
    legacy = {"id": "legacy", "citation_keys": ["A"], "support_status": "unsupported"}

    assert support._support_groups_for_quality_items([v3_a, v3_b, legacy]) == [[v3_a], [v3_b], [legacy]]
    assert support._support_groups_for_quality_items([legacy]) == [[legacy]]
    assert support._support_groups_for_quality_items([]) == [[]]


def test_quality_support_preserves_legacy_items_and_status_order() -> None:
    legacy_items = [
        {"id": "ok", "citation_keys": ["A"], "support_status": "supported"},
        {"id": "bad", "citation_keys": ["A"], "support_status": "unsupported"},
        "not-an-item",
    ]

    assert support._support_items({"items": legacy_items}) == legacy_items[:2]
    assert support._support_by_key(legacy_items[:2]) == {"A": legacy_items[:2]}
    assert support._worst_support_status(legacy_items[:2]) == "unsupported"


def test_quality_support_public_case_and_stable_redacted_ids() -> None:
    v3_item = {"id": "v3", "case_id": "case-v3", "citation_keys": ["KeyA"], "review_schema": "citation-support-review/3"}

    assert support._public_case_id([v3_item], [{"id": "claim-1"}]) == "case-v3"
    assert support._public_case_id([], [{"id": "claim-1"}]) == "claim-1"
    assert support._quality_item_id("KeyA", [v3_item], group_index=2).startswith("redacted-citation-item:")
    assert support._quality_item_id("KeyA", [], group_index=0) == support._quality_item_id("KeyA", [], group_index=99)


def test_quality_support_public_failure_message_uses_public_code_mapping() -> None:
    human_needed_item = {"review_schema": "citation-support-review/3", "verdict": "human_needed"}

    assert support._public_failure_message([human_needed_item], ["critical_unsupported_citation"]) == (
        "Source requires manual evidence."
    )
    assert support._public_failure_message([], ["critical_unsupported_citation"]) == (
        "Citation support is insufficient for a required claim."
    )
