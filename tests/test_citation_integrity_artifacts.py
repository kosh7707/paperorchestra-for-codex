from __future__ import annotations

import json
from pathlib import Path

from paperorchestra.reviews import citation_integrity_artifacts


def _write_json(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_payload_status_accepts_status_verdict_and_overall_status() -> None:
    assert citation_integrity_artifacts._payload_status({"status": "PASS"}) == "pass"
    assert citation_integrity_artifacts._payload_status({"verdict": "Blocked"}) == "blocked"
    assert citation_integrity_artifacts._payload_status({"overall_status": "warning"}) == "warning"
    assert citation_integrity_artifacts._payload_status([]) is None


def test_artifact_check_fails_closed_for_missing_unbound_stale_and_failed_payload(tmp_path: Path) -> None:
    missing = citation_integrity_artifacts._artifact_check(
        tmp_path / "missing.json",
        expected_manuscript_sha256="expected",
        missing_code="missing",
        stale_code="stale",
        failed_code="failed",
    )
    assert missing["status"] == "fail"
    assert missing["failing_codes"] == ["missing"]
    assert missing["reason"] == "missing_or_unreadable"

    path = _write_json(
        tmp_path / "payload.json",
        {"status": "fail", "manuscript_sha256": "actual", "failing_codes": ["extra", "failed"]},
    )
    checked = citation_integrity_artifacts._artifact_check(
        path,
        expected_manuscript_sha256="expected",
        missing_code="missing",
        stale_code="stale",
        failed_code="failed",
        unbound_code="unbound",
        require_binding=True,
    )
    assert checked["status"] == "fail"
    assert checked["artifact_status"] == "fail"
    assert checked["manuscript_sha256"] == "actual"
    assert checked["expected_manuscript_sha256"] == "expected"
    assert checked["failing_codes"] == ["extra", "failed", "stale"]

    unbound_path = _write_json(tmp_path / "unbound.json", {"status": "pass"})
    unbound = citation_integrity_artifacts._artifact_check(
        unbound_path,
        expected_manuscript_sha256="expected",
        missing_code="missing",
        stale_code="stale",
        failed_code="failed",
        unbound_code="unbound",
        require_binding=True,
    )
    assert unbound["failing_codes"] == ["unbound"]


def test_critic_review_artifact_accepts_warn_and_deduplicates_failures(tmp_path: Path) -> None:
    passing_path = _write_json(tmp_path / "pass.json", {"status": "warn", "manuscript_sha256": "sha"})
    passing = citation_integrity_artifacts._critic_review_artifact(
        "rendered_reference_audit",
        passing_path,
        expected_manuscript_sha256="sha",
        require_binding=True,
    )
    assert passing["status"] == "pass"
    assert passing["artifact_status"] == "warn"

    failing_path = _write_json(
        tmp_path / "fail.json",
        {"status": "skip", "failing_codes": ["custom", "custom"]},
    )
    failing = citation_integrity_artifacts._critic_review_artifact(
        "citation_intent_plan",
        failing_path,
        expected_manuscript_sha256="sha",
        require_binding=True,
    )
    assert failing["status"] == "fail"
    assert failing["failing_codes"] == ["citation_intent_plan_skip", "citation_intent_plan_unbound", "custom"]
