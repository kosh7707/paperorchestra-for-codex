from __future__ import annotations

from typing import Any, Mapping

from paperorchestra.orchestra.acceptance_contract import _ALLOWED_EVIDENCE_KEYS
from paperorchestra.orchestra.acceptance_safety import (
    REDACTED,
    _SHA256_RE,
    _reject_forbidden_keys,
    _validate_kind,
    _validate_public_path,
    _validate_public_string,
)


def validate_evidence_refs(value: Any, *, gate_id: str) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"evidence_refs for {gate_id} must be a list.")
    refs: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise ValueError(f"evidence_refs[{index}] for {gate_id} must be an object.")
        _reject_forbidden_keys(item, gate_id=gate_id)
        extra_keys = set(item) - _ALLOWED_EVIDENCE_KEYS
        if extra_keys:
            raise ValueError(f"Unsupported evidence ref key for {gate_id}: {sorted(extra_keys)[0]}")
        ref: dict[str, str] = {}
        for key in ("kind", "summary", "path", "sha256"):
            if key not in item or item[key] is None:
                continue
            if not isinstance(item[key], str):
                raise ValueError(f"evidence ref {key} for {gate_id} must be a string.")
            text = item[key]
            if key == "kind":
                _validate_kind(text, gate_id=gate_id)
            else:
                _validate_public_string(text, gate_id=gate_id, field=key)
            if key == "path":
                _validate_public_path(text, gate_id=gate_id)
            if key == "sha256" and text != REDACTED and not _SHA256_RE.fullmatch(text):
                raise ValueError(f"sha256 for {gate_id} must be 64 hex characters.")
            ref[key] = text
        refs.append(ref)
    return refs


def validate_notes(value: Any, *, gate_id: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"notes for {gate_id} must be a list.")
    notes: list[str] = []
    for index, item in enumerate(value):
        if isinstance(item, Mapping):
            _reject_forbidden_keys(item, gate_id=gate_id)
            raise ValueError(f"notes[{index}] for {gate_id} must be a string.")
        if not isinstance(item, str):
            raise ValueError(f"notes[{index}] for {gate_id} must be a string.")
        _validate_public_string(item, gate_id=gate_id, field="notes")
        notes.append(item)
    return notes
