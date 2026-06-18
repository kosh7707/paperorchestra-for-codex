from __future__ import annotations

import re
from typing import Any, Mapping

from paperorchestra.orchestra.acceptance_safety import _reject_forbidden_keys, _validate_public_path, _validate_public_string
from paperorchestra.orchestra.final_audit_bug_constants import (
    ALLOWED_FINAL_AUDIT_BUG_KEYS,
    ALLOWED_FINAL_AUDIT_BUG_SEVERITIES,
    ALLOWED_FINAL_AUDIT_BUG_STATUSES,
    REQUIRED_FINAL_AUDIT_BUG_KEYS,
)


def validate_final_audit_bug_record(value: Any, *, index: int) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"final audit bug[{index}] must be an object.")
    _reject_forbidden_keys(value, gate_id=f"final_audit_bug[{index}]")
    _validate_final_audit_bug_shape(value, index=index)
    return _clean_final_audit_bug_record(value, index=index)


def _validate_final_audit_bug_shape(value: Mapping[str, Any], *, index: int) -> None:
    extra_keys = set(value) - ALLOWED_FINAL_AUDIT_BUG_KEYS
    if extra_keys:
        raise ValueError(f"Unsupported final audit bug key: {sorted(extra_keys)[0]}")
    missing = [key for key in sorted(REQUIRED_FINAL_AUDIT_BUG_KEYS) if not str(value.get(key) or "").strip()]
    if missing:
        raise ValueError(f"final audit bug[{index}] is missing required field: {missing[0]}")
    status = str(value["status"])
    if status not in ALLOWED_FINAL_AUDIT_BUG_STATUSES:
        raise ValueError(f"Invalid final audit bug status: {status}")
    severity = str(value["severity"])
    if severity not in ALLOWED_FINAL_AUDIT_BUG_SEVERITIES:
        raise ValueError(f"Invalid final audit bug severity: {severity}")
    if status in {"fixed", "deferred", "known_limitation"} and not str(value.get("resolution") or "").strip():
        raise ValueError(f"final audit bug[{index}] status={status} requires a resolution.")


def _clean_final_audit_bug_record(value: Mapping[str, Any], *, index: int) -> dict[str, Any]:
    record: dict[str, Any] = {}
    for key in sorted(REQUIRED_FINAL_AUDIT_BUG_KEYS | {"resolution", "notes"}):
        if key not in value or value[key] is None:
            continue
        if key == "notes":
            cleaned_notes = _clean_public_notes(value[key], index=index)
            if cleaned_notes:
                record[key] = cleaned_notes
            continue
        record[key] = _clean_public_field(value[key], index=index, key=key)
    return record


def _clean_public_notes(value: Any, *, index: int) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"final audit bug[{index}].notes must be a list.")
    cleaned_notes: list[str] = []
    for note_index, note in enumerate(value):
        if not isinstance(note, str):
            raise ValueError(f"final audit bug[{index}].notes[{note_index}] must be a string.")
        _validate_public_string(note, gate_id=f"final_audit_bug[{index}]", field="notes")
        cleaned_notes.append(note)
    return cleaned_notes


def _clean_public_field(value: Any, *, index: int, key: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"final audit bug[{index}].{key} must be a string.")
    _validate_public_string(value, gate_id=f"final_audit_bug[{index}]", field=key)
    if key == "artifact_ref":
        _validate_public_path(value, gate_id=f"final_audit_bug[{index}]")
    if key in {"id", "phase", "gate"} and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]*", value):
        raise ValueError(f"Unsafe final audit bug {key}: {value}")
    return value
