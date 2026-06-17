from __future__ import annotations

from typing import Any


def _strict_issue_codes(reproducibility: dict[str, Any], *, kinds: set[str] | None = None) -> list[str]:
    codes: list[str] = []
    for issue in reproducibility.get("strict_content_gate_issues") or []:
        if not isinstance(issue, dict):
            continue
        if kinds is not None and str(issue.get("kind") or "") not in kinds:
            continue
        code = str(issue.get("code") or "")
        if code:
            codes.append(code)
    return codes


def _tier(
    *,
    status: str,
    checks: dict[str, Any] | None = None,
    failing_codes: list[str] | None = None,
    skip_reason: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": status,
        "checks": checks or {},
    }
    if failing_codes is not None:
        payload["failing_codes"] = sorted(dict.fromkeys(str(code) for code in failing_codes if code))
    if skip_reason:
        payload["skip_reason"] = skip_reason
    payload.update(extra)
    return payload


def _skipped_tier(reason: str) -> dict[str, Any]:
    return _tier(status="skipped_due_to_upstream_fail", checks={}, failing_codes=[], skip_reason=reason)


def _status_from_failures(failing_codes: list[str], *, warn_only: bool = False) -> str:
    if not failing_codes:
        return "pass"
    return "warn" if warn_only else "fail"
