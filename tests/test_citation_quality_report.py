from __future__ import annotations

import pytest

from paperorchestra.reviews import citation_quality
from paperorchestra.reviews import citation_quality_report


def test_public_report_summarizes_items_without_internal_fields() -> None:
    item = citation_quality_report.CitationQualityItem(
        item_id="internal-1",
        citation_key="KeyA",
        claim_id="Claim1",
        citation_key_sha256="abc",
        critical=True,
        need_status="required",
        support_status="unsupported",
        metadata_status="known",
        severity="blocker",
        failing_codes=["critical_unsupported_citation"],
        public_case="case-1",
        public_failure_code="human_needed",
        public_failure_message="Manual evidence is required.",
    )
    report = citation_quality_report.CitationQualityGateReport(
        status="fail",
        quality_mode="claim_safe",
        manuscript_sha256="sha",
        hard_gate_failures=["critical_unsupported_citation"],
        warning_codes=[],
        counts={"critical_need_count": 1, "critical_unsupported_count": 1},
        items=[item],
    )

    public = report.to_public_dict()
    internal = report.to_internal_dict()

    assert public["schema"] == citation_quality.CITATION_QUALITY_GATE_SCHEMA_VERSION
    assert public["summary"] == {"pass": 0, "weak": 0, "fail": 1, "human_needed": 0}
    assert public["failures"] == [
        {"case": "case-1", "key": "KeyA", "code": "human_needed", "message": "Manual evidence is required."}
    ]
    assert "items" not in public
    assert internal["items"][0]["citation_keys_sha256"] == ["abc"]


def test_public_safe_rejects_private_marker_values() -> None:
    with pytest.raises(ValueError, match="private marker"):
        citation_quality_report._assert_public_safe({"failures": [{"message": "contains PRIVATE token"}]})
