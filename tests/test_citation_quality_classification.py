from __future__ import annotations

from paperorchestra.reviews.citation_quality_counts import _counts, _integrity_warning_codes
from paperorchestra.reviews.citation_quality_indices import _claims_by_key, _roles_by_key
from paperorchestra.reviews.citation_quality_policy import _is_critical_key, _is_explicitly_noncritical
from paperorchestra.reviews.citation_quality_report import CitationQualityItem


def test_claims_and_roles_are_indexed_by_citation_key() -> None:
    claims = _claims_by_key(
        {
            "claims": [
                {"id": "C1", "citation_keys": [" KeyA ", "KeyB"]},
                {"id": "C2", "citation_keys": ["KeyA"]},
                "not-a-claim",
            ]
        }
    )
    roles = _roles_by_key(
        {
            "placements": [
                {"citation_key": "KeyA", "citation_role": "Motivation", "claim_ids": ["C1"]},
                {"citation_keys": ["KeyB"], "support_role": "Background", "criticality": "low"},
            ]
        }
    )

    assert [claim["id"] for claim in claims["KeyA"]] == ["C1", "C2"]
    assert claims["KeyB"][0]["id"] == "C1"
    assert roles["KeyA"] == {"motivation", "c1"}
    assert roles["KeyB"] == {"background", "low"}


def test_criticality_policy_covers_support_claim_role_and_claim_safe_metadata() -> None:
    assert _is_critical_key(
        "A",
        [{"critical": True}],
        [],
        set(),
        mode="draft",
        metadata_problem=False,
    )
    assert _is_critical_key(
        "A",
        [{"claim_type": "numeric"}],
        [],
        set(),
        mode="draft",
        metadata_problem=False,
    )
    assert _is_critical_key(
        "A",
        [],
        [{"required_source_type": "prior_work"}],
        set(),
        mode="draft",
        metadata_problem=False,
    )
    assert _is_critical_key("A", [], [], {"result"}, mode="draft", metadata_problem=False)
    assert _is_critical_key("A", [], [], set(), mode="claim_safe", metadata_problem=True)
    assert not _is_critical_key("A", [], [], set(), mode="draft", metadata_problem=True)


def test_noncritical_policy_yields_to_required_or_high_criticality() -> None:
    assert _is_explicitly_noncritical([], {"background"})
    assert not _is_explicitly_noncritical([], {"background", "critical"})
    assert not _is_explicitly_noncritical([{"citation_required": True, "claim_type": "background"}], set())
    assert not _is_explicitly_noncritical([{"required_source_type": "standard", "claim_type": "optional"}], set())
    assert _is_explicitly_noncritical([{"claim_type": "optional"}], set())


def test_integrity_warning_codes_and_counts_extract_gate_relevant_numbers() -> None:
    item_fail = CitationQualityItem(
        item_id="i1",
        citation_key="A",
        claim_id=None,
        citation_key_sha256="sha-a",
        critical=True,
        need_status="required",
        support_status="unsupported",
        metadata_status="known",
        severity="blocker",
        failing_codes=["critical_unsupported_citation"],
    )
    item_warn = CitationQualityItem(
        item_id="i2",
        citation_key="B",
        claim_id=None,
        citation_key_sha256="sha-b",
        critical=False,
        need_status="unknown",
        support_status="supported",
        metadata_status="known",
        severity="warning",
        warning_codes=["noncritical_weak_reference_identity"],
    )
    integrity = {
        "warning_codes": ["citation_bomb_detected", "irrelevant"],
        "checks": {
            "citation_density": {
                "warning_codes": ["dense_citation_bundle_requires_role_check"],
                "bomb_sentences": ["s1"],
                "bomb_paragraph_key_sets": [["A", "B"]],
            },
            "duplicate_support": {"duplicate_keys": ["A"]},
        },
    }

    assert _integrity_warning_codes(integrity) == [
        "citation_bomb_detected",
        "dense_citation_bundle_requires_role_check",
    ]
    assert _counts([item_fail, item_warn], integrity) == {
        "critical_need_count": 1,
        "critical_unknown_reference_count": 0,
        "critical_unsupported_count": 1,
        "critical_weak_identity_count": 0,
        "noncritical_weak_identity_count": 1,
        "citation_bomb_count": 2,
        "duplicate_reference_count": 1,
    }
