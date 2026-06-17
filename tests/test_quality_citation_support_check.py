from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from paperorchestra.loop_engine.quality.citation_support import _citation_support_check
from paperorchestra.loop_engine.quality.utils import _file_sha256


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def _state_with_legacy_review(tmp_path: Path, *, support_status: str = "supported", manuscript_sha: str | None = None) -> SimpleNamespace:
    paper = tmp_path / "paper.tex"
    paper.write_text("Prior work supports the setup \\cite{KeyA}.\n", encoding="utf-8")
    citation_map = tmp_path / "citation_map.json"
    _write_json(
        citation_map,
        {
            "KeyA": {
                "title": "Known Source",
                "url": "https://example.test/source",
                "authors": ["A. Author"],
                "year": "2024",
            }
        },
    )
    item = {
        "id": "S1",
        "sentence": "Prior work supports the setup \\cite{KeyA}.",
        "citation_keys": ["KeyA"],
        "support_status": support_status,
        "evidence": [
            {
                "citation_key": "KeyA",
                "source_title": "Known Source",
                "source_url": "https://example.test/source",
                "evidence_quote_or_summary": "Known Source describes the setup.",
                "supports_claim": True,
            }
        ],
    }
    review = tmp_path / "citation_support_review.json"
    _write_json(
        review,
        {
            "schema_version": "citation-support-review/2",
            "manuscript_sha256": manuscript_sha or _file_sha256(paper),
            "citation_map_sha256": _file_sha256(citation_map),
            "claims_checked": 1,
            "summary": {support_status: 1},
            "items": [item],
            "evidence_provenance": {"claim_support_not_metadata_lookup": True, "mode": "source"},
        },
    )
    return SimpleNamespace(artifacts=SimpleNamespace(paper_full_tex=str(paper), citation_map_json=str(citation_map)))


def test_legacy_citation_support_check_passes_supported_source_evidence(tmp_path: Path) -> None:
    state = _state_with_legacy_review(tmp_path)

    result = _citation_support_check(tmp_path, state)

    assert result["status"] == "pass"
    assert result["failing_codes"] == []
    assert result["summary"] == {"supported": 1}
    assert result["unsupported_count"] == 0
    assert result["evidence_missing_count"] == 0
    assert result["legacy_untrusted"] is False
    assert result["claims_checked"] == 1
    assert result["item_count"] == 1
    assert result["current_cited_sentence_count"] == 1


def test_legacy_citation_support_check_reports_stale_review_before_item_analysis(tmp_path: Path) -> None:
    state = _state_with_legacy_review(tmp_path, manuscript_sha="old-sha")
    current_sha = _file_sha256(state.artifacts.paper_full_tex)

    result = _citation_support_check(tmp_path, state)

    assert result["status"] == "fail"
    assert result["failing_codes"] == ["citation_support_review_stale"]
    assert result["summary"] is None
    assert result["expected_manuscript_sha256"] == current_sha
    assert result["actual_manuscript_sha256"] == "old-sha"


def test_legacy_citation_support_check_canonicalizes_manual_and_invalid_status(tmp_path: Path) -> None:
    state = _state_with_legacy_review(tmp_path, support_status="not_a_status")

    result = _citation_support_check(tmp_path, state)

    assert result["status"] == "fail"
    assert result["summary"] == {"not_a_status": 1}
    assert result["invalid_status_count"] == 1
    assert result["invalid_status_values"] == ["not_a_status"]
    assert "citation_support_invalid_status" in result["failing_codes"]
    assert "citation_support_summary_mismatch" not in result["failing_codes"]
