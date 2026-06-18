from __future__ import annotations

from typing import Any, Mapping

from paperorchestra.orchestra.final_audit_bug_constants import (
    ALLOWED_FINAL_AUDIT_BUG_KEYS as _ALLOWED_FINAL_AUDIT_BUG_KEYS,
    ALLOWED_FINAL_AUDIT_BUG_SEVERITIES as _ALLOWED_FINAL_AUDIT_BUG_SEVERITIES,
    ALLOWED_FINAL_AUDIT_BUG_STATUSES as _ALLOWED_FINAL_AUDIT_BUG_STATUSES,
    FINAL_AUDIT_BUG_LEDGER_SCHEMA_VERSION,
    REQUIRED_FINAL_AUDIT_BUG_KEYS as _REQUIRED_FINAL_AUDIT_BUG_KEYS,
)
from paperorchestra.orchestra.final_audit_bug_records import validate_final_audit_bug_record as _validate_final_audit_bug_record
from paperorchestra.orchestra.final_audit_bug_summary import final_audit_bug_overall_status, render_final_audit_bug_ledger_summary


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
    return {
        "schema_version": FINAL_AUDIT_BUG_LEDGER_SCHEMA_VERSION,
        "overall_status": final_audit_bug_overall_status(bugs),
        "bug_count": len(bugs),
        "bugs": bugs,
        "private_safe_summary": True,
    }


__all__ = [
    "FINAL_AUDIT_BUG_LEDGER_SCHEMA_VERSION",
    "_ALLOWED_FINAL_AUDIT_BUG_KEYS",
    "_ALLOWED_FINAL_AUDIT_BUG_SEVERITIES",
    "_ALLOWED_FINAL_AUDIT_BUG_STATUSES",
    "_REQUIRED_FINAL_AUDIT_BUG_KEYS",
    "_validate_final_audit_bug_record",
    "build_final_audit_bug_ledger",
    "render_final_audit_bug_ledger_summary",
]
