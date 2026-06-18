from __future__ import annotations

import json
from pathlib import Path

from paperorchestra.core.session import runtime_root
from paperorchestra.loop_engine.quality import provenance
from paperorchestra.loop_engine.quality.utils import _sha256_jsonable


def test_provenance_trust_classifies_mock_mixed_and_live_evidence() -> None:
    assert provenance._provenance_trust({"latest_provider_name": "mock"})["level"] == "mock"

    mixed = provenance._provenance_trust(
        {
            "prompt_trace_file_count": 0,
            "lane_manifest_summary": {"manifest_count": 0},
            "verification_invoked": False,
            "citation_live_provenance": {"status": "missing"},
        }
    )
    assert mixed["level"] == "mixed"
    assert mixed["watermark_required"] is True
    assert "prompt_trace_missing" in mixed["mixed_evidence"]
    assert "citation_registry_live_verification_not_invoked" in mixed["mixed_evidence"]

    live = provenance._provenance_trust(
        {
            "prompt_trace_file_count": 2,
            "lane_manifest_summary": {"manifest_count": 1},
            "verification_invoked": True,
            "citation_support_review_live": True,
            "citation_live_provenance": {"status": "pass", "live_verified_count": 3},
        }
    )
    assert live["level"] == "live"
    assert live["watermark_required"] is False
    assert live["citation_registry_live_verified_count"] == 3


def test_mixed_provenance_acceptance_requires_independent_fresh_bound_payload(tmp_path: Path) -> None:
    quality = {
        "manuscript_hash": "m" * 64,
        "provenance_trust": {
            "level": "mixed",
            "mock_evidence": [],
            "mixed_evidence": ["prompt_trace_missing"],
            "watermark_required": True,
        },
    }

    missing = provenance._mixed_provenance_acceptance(tmp_path, quality)
    assert missing["status"] == "missing"
    assert missing["failing_codes"] == ["mixed_provenance_acceptance_missing"]

    path = runtime_root(tmp_path) / "mixed-provenance-acceptance.json"
    expected_sha = "sha256:" + _sha256_jsonable(quality["provenance_trust"])
    path.write_text(
        json.dumps(
            {
                "schema_version": "mixed-provenance-acceptance/1",
                "source": "human_reviewer",
                "not_independent_human_review": False,
                "manuscript_sha256": quality["manuscript_hash"],
                "provenance_trust_sha256": expected_sha,
                "operator_label": "reviewer-a",
                "accepted_at": "2026-06-17T00:00:00Z",
                "rationale": "Reviewed mixed provenance and accepted with watermark.",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    accepted = provenance._mixed_provenance_acceptance(tmp_path, quality)
    assert accepted["status"] == "pass"
    assert accepted["failing_codes"] == []
    assert accepted["sha256"]

    stale = dict(quality)
    stale["manuscript_hash"] = "0" * 64
    assert "mixed_provenance_acceptance_stale" in provenance._mixed_provenance_acceptance(tmp_path, stale)["failing_codes"]


def test_mixed_provenance_acceptance_rejects_operator_or_incomplete_payload(tmp_path: Path) -> None:
    quality = {"manuscript_hash": "m" * 64, "provenance_trust": {"level": "mixed"}}
    path = runtime_root(tmp_path) / "mixed-provenance-acceptance.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "legacy",
                "source": "codex_operator",
                "not_independent_human_review": True,
                "manuscript_sha256": quality["manuscript_hash"],
                "provenance_trust_sha256": "wrong",
                "operator_label": "",
                "accepted_at": "",
                "rationale": "short",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = provenance._mixed_provenance_acceptance(tmp_path, quality)
    assert result["status"] == "fail"
    assert result["failing_codes"] == [
        "mixed_provenance_acceptance_incomplete",
        "mixed_provenance_acceptance_legacy_untrusted",
        "mixed_provenance_acceptance_operator_not_independent",
        "mixed_provenance_acceptance_stale",
    ]
