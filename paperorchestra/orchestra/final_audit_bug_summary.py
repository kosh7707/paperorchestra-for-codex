from __future__ import annotations

from typing import Any, Mapping

from paperorchestra.orchestra.final_audit_bug_constants import ALLOWED_FINAL_AUDIT_BUG_STATUSES


def final_audit_bug_overall_status(bugs: list[dict[str, Any]]) -> str:
    statuses = [bug["status"] for bug in bugs]
    if "open" in statuses:
        return "failed"
    if "deferred" in statuses:
        return "blocked"
    return "pass"


def render_final_audit_bug_ledger_summary(ledger: Mapping[str, Any]) -> str:
    bugs = ledger.get("bugs") if isinstance(ledger.get("bugs"), list) else []
    counts = {status: 0 for status in sorted(ALLOWED_FINAL_AUDIT_BUG_STATUSES)}
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
