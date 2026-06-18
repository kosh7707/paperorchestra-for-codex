from __future__ import annotations

FINAL_AUDIT_BUG_LEDGER_SCHEMA_VERSION = "orchestrator-final-audit-bug-ledger/1"
ALLOWED_FINAL_AUDIT_BUG_STATUSES = {"open", "fixed", "deferred", "known_limitation"}
ALLOWED_FINAL_AUDIT_BUG_SEVERITIES = {"blocker", "critical", "major", "minor", "info"}
ALLOWED_FINAL_AUDIT_BUG_KEYS = {
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
REQUIRED_FINAL_AUDIT_BUG_KEYS = {
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
