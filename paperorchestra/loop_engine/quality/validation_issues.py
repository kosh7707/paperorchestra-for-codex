from __future__ import annotations

from typing import Any

from .policy import TIER2_CLAIM_CODES
from .utils import _read_json_if_exists


def _validation_issue_counts(reproducibility: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for report in reproducibility.get("validation_warning_reports") or []:
        payload = _read_json_if_exists(report.get("path"))
        if not isinstance(payload, dict):
            continue
        for issue in payload.get("issues") or []:
            if not isinstance(issue, dict):
                continue
            code = str(issue.get("code") or "")
            if code:
                counts[code] = counts.get(code, 0) + 1
    for issue in reproducibility.get("strict_content_gate_issues") or []:
        if not isinstance(issue, dict):
            continue
        code = str(issue.get("code") or "")
        if code in TIER2_CLAIM_CODES:
            counts[code] = max(counts.get(code, 0), 1)
    return counts
