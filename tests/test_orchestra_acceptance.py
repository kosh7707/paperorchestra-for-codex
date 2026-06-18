from __future__ import annotations

import pytest

from paperorchestra.orchestra import acceptance_ledger, final_audit_bug_ledger


def _bug(status: str = "open", *, resolution: str | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "bug-1",
        "severity": "major",
        "status": status,
        "command": "qa-loop",
        "phase": "final_audit",
        "gate": "compile_export",
        "artifact_ref": "artifacts/final-audit.json",
        "expected": "compiled evidence bundle",
        "actual": "compile artifact missing",
        "notes": ["public note"],
    }
    if resolution is not None:
        payload["resolution"] = resolution
    return payload


def test_final_audit_bug_ledger_status_and_summary_are_stable() -> None:
    ledger = final_audit_bug_ledger.build_final_audit_bug_ledger(
        {
            "bugs": [
                _bug("fixed", resolution="recompiled successfully"),
                _bug("deferred", resolution="needs human venue decision"),
            ]
        }
    )

    assert ledger["schema_version"] == final_audit_bug_ledger.FINAL_AUDIT_BUG_LEDGER_SCHEMA_VERSION
    assert ledger["overall_status"] == "blocked"
    assert ledger["bug_count"] == 2
    assert ledger["private_safe_summary"] is True
    assert ledger["bugs"][0]["resolution"] == "recompiled successfully"

    summary = final_audit_bug_ledger.render_final_audit_bug_ledger_summary(ledger)

    assert "Final audit bug ledger" in summary
    assert "overall: blocked" in summary
    assert "deferred: 1" in summary
    assert "fixed: 1" in summary
    assert "  - bug-1" in summary


def test_final_audit_bug_ledger_rejects_private_paths_commands_and_missing_resolution() -> None:
    with pytest.raises(ValueError, match="requires a resolution"):
        final_audit_bug_ledger.build_final_audit_bug_ledger({"bugs": [_bug("fixed")]})
    with pytest.raises(ValueError, match="Unsafe raw command text"):
        final_audit_bug_ledger.build_final_audit_bug_ledger({"bugs": [{**_bug(), "command": "omx trace summary"}]})
    with pytest.raises(ValueError, match="must be workspace-relative"):
        final_audit_bug_ledger.build_final_audit_bug_ledger({"bugs": [{**_bug(), "artifact_ref": "../outside.json"}]})
    with pytest.raises(ValueError, match="Unsafe private marker"):
        final_audit_bug_ledger.build_final_audit_bug_ledger({"bugs": [{**_bug(), "actual": "TOKEN leaked"}]})


def test_acceptance_ledger_still_rejects_unsafe_evidence_after_safety_split() -> None:
    gate_id = acceptance_ledger.ACCEPTANCE_GATE_IDS[0]
    safe_sha = "a" * 64

    acceptance_ledger.build_acceptance_ledger(
        {gate_id: {"status": "pass", "evidence_refs": [{"kind": "unit", "path": "artifacts/report.json", "sha256": safe_sha}]}}
    )

    unsafe_cases = [
        ({"evidence_refs": [{"kind": "unit", "summary": "run omx status"}]}, "Unsafe raw command text"),
        ({"evidence_refs": [{"kind": "unit", "summary": "SECRET leaked"}]}, "Unsafe private marker"),
        ({"evidence_refs": [{"kind": "unit", "path": "../outside.json"}]}, "workspace-relative"),
        ({"evidence_refs": [{"kind": "unit", "sha256": "not-a-hash"}]}, "64 hex"),
        ({"notes": [{"raw_text": "hidden"}]}, "Unsafe evidence key"),
    ]
    for entry, message in unsafe_cases:
        with pytest.raises(ValueError, match=message):
            acceptance_ledger.build_acceptance_ledger({gate_id: {"status": "pass", **entry}})
