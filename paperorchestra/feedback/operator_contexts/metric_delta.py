from __future__ import annotations

from typing import Any


def _compact_metric_delta_records(records: Any, *, limit: int = 8) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if not isinstance(records, list):
        return result
    for record in records:
        if not isinstance(record, dict):
            continue
        compact = {
            "code": str(record.get("code") or ""),
            "before": record.get("before"),
            "after": record.get("after"),
            "delta": record.get("delta"),
        }
        if compact["code"]:
            result.append(compact)
        if len(result) >= limit:
            break
    return result
