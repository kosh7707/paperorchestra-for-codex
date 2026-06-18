from __future__ import annotations


def _public_blocking_reason(reason: str) -> str:
    if reason.startswith("unknown_score_dimension:"):
        return "unknown_score_dimension:<redacted>"
    return reason
