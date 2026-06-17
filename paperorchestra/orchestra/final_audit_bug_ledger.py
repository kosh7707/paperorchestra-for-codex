from __future__ import annotations

import re
from typing import Any, Mapping

from paperorchestra.orchestra.acceptance_safety import (
    _reject_forbidden_keys,
    _validate_public_path,
    _validate_public_string,
)

FINAL_AUDIT_BUG_LEDGER_SCHEMA_VERSION = "orchestrator-final-audit-bug-ledger/1"
_ALLOWED_FINAL_AUDIT_BUG_STATUSES = {"open", "fixed", "deferred", "known_limitation"}
_ALLOWED_FINAL_AUDIT_BUG_SEVERITIES = {"blocker", "critical", "major", "minor", "info"}
_ALLOWED_FINAL_AUDIT_BUG_KEYS = {
    "id",
    "severity",
    "status",
    "command",
    "phase",
    "gate",
    "artifact_ref",
    "expected",
    "actual",
    "resolution",
    "notes",
}
_REQUIRED_FINAL_AUDIT_BUG_KEYS = {
    "id",
    "severity",
    "status",
    "command",
    "phase",
    "gate",
    "artifact_ref",
    "expected",
    "actual",
}


def build_final_audit_bug_ledger(payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if payload is None:
        payload = {"bugs": []}
    if not isinstance(payload, Mapping):
        raise ValueError("Final audit bug ledger payload must be an object.")
    if "bugs" not in payload:
        raise ValueError("Final audit bug ledger payload must contain a top-level bugs list.")
    bugs_payload = payload.get("bugs", [])
    if not isinstance(bugs_payload, list):
        raise ValueError("Final audit bug ledger bugs must be a list.")
    bugs = [_validate_final_audit_bug_record(item, index=index) for index, item in enumerate(bugs_payload)]
    statuses = [bug["status"] for bug in bugs]
    if "open" in statuses:
        overall_status = "failed"
    elif "deferred" in statuses:
        overall_status = "blocked"
    else:
        overall_status = "pass"
    return {
        "schema_version": FINAL_AUDIT_BUG_LEDGER_SCHEMA_VERSION,
        "overall_status": overall_status,
        "bug_count": len(bugs),
        "bugs": bugs,
        "private_safe_summary": True,
    }


def render_final_audit_bug_ledger_summary(ledger: Mapping[str, Any]) -> str:
    bugs = ledger.get("bugs") if isinstance(ledger.get("bugs"), list) else []
    counts = {status: 0 for status in sorted(_ALLOWED_FINAL_AUDIT_BUG_STATUSES)}
    for bug in bugs:
        if isinstance(bug, Mapping):
            status = str(bug.get("status") or "")
            if status in counts:
                counts[status] += 1
    lines = [
        "Final audit bug ledger",
        f"overall: {ledger.get('overall_status', 'unknown')}",
        f"bugs: {ledger.get('bug_count', len(bugs))}",
    ]
    lines.extend(f"{status}: {counts[status]}" for status in sorted(counts))
    open_ids = [str(bug.get("id")) for bug in bugs if isinstance(bug, Mapping) and bug.get("status") in {"open", "deferred"}][:5]
    if open_ids:
        lines.append("open/deferred bugs:")
        lines.extend(f"  - {bug_id}" for bug_id in open_ids)
    return "\n".join(lines)


def _validate_final_audit_bug_record(value: Any, *, index: int) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"final audit bug[{index}] must be an object.")
    _reject_forbidden_keys(value, gate_id=f"final_audit_bug[{index}]")
    extra_keys = set(value) - _ALLOWED_FINAL_AUDIT_BUG_KEYS
    if extra_keys:
        raise ValueError(f"Unsupported final audit bug key: {sorted(extra_keys)[0]}")
    missing = [key for key in sorted(_REQUIRED_FINAL_AUDIT_BUG_KEYS) if not str(value.get(key) or "").strip()]
    if missing:
        raise ValueError(f"final audit bug[{index}] is missing required field: {missing[0]}")
    status = str(value["status"])
    if status not in _ALLOWED_FINAL_AUDIT_BUG_STATUSES:
        raise ValueError(f"Invalid final audit bug status: {status}")
    severity = str(value["severity"])
    if severity not in _ALLOWED_FINAL_AUDIT_BUG_SEVERITIES:
        raise ValueError(f"Invalid final audit bug severity: {severity}")
    if status in {"fixed", "deferred", "known_limitation"} and not str(value.get("resolution") or "").strip():
        raise ValueError(f"final audit bug[{index}] status={status} requires a resolution.")

    record: dict[str, Any] = {}
    for key in sorted(_REQUIRED_FINAL_AUDIT_BUG_KEYS | {"resolution", "notes"}):
        if key not in value or value[key] is None:
            continue
        if key == "notes":
            notes = value[key]
            if not isinstance(notes, list):
                raise ValueError(f"final audit bug[{index}].notes must be a list.")
            cleaned_notes: list[str] = []
            for note_index, note in enumerate(notes):
                if not isinstance(note, str):
                    raise ValueError(f"final audit bug[{index}].notes[{note_index}] must be a string.")
                _validate_public_string(note, gate_id=f"final_audit_bug[{index}]", field="notes")
                cleaned_notes.append(note)
            if cleaned_notes:
                record[key] = cleaned_notes
            continue
        if not isinstance(value[key], str):
            raise ValueError(f"final audit bug[{index}].{key} must be a string.")
        text = value[key]
        _validate_public_string(text, gate_id=f"final_audit_bug[{index}]", field=key)
        if key == "artifact_ref":
            _validate_public_path(text, gate_id=f"final_audit_bug[{index}]")
        if key in {"id", "phase", "gate"} and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]*", text):
            raise ValueError(f"Unsafe final audit bug {key}: {text}")
        record[key] = text
    return record

