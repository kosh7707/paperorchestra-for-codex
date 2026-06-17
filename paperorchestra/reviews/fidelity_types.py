from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class FidelityCheck:
    code: str
    status: str  # implemented | partial | missing
    rationale: str
    next_step: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def status_histogram(checks: Sequence[FidelityCheck]) -> dict[str, int]:
    counts = Counter(check.status for check in checks)
    return {
        "missing": counts.get("missing", 0),
        "partial": counts.get("partial", 0),
        "implemented": counts.get("implemented", 0),
    }


def overall_status(checks: Sequence[FidelityCheck]) -> str:
    if not checks:
        return "missing"
    histogram = status_histogram(checks)
    if histogram["implemented"] == len(checks):
        return "implemented"
    if histogram["missing"] == len(checks):
        return "missing"
    return "partial"


def summary_descriptor(checks: Sequence[FidelityCheck]) -> str:
    if not checks:
        return "missing"
    histogram = status_histogram(checks)
    if histogram["implemented"] == len(checks):
        return "complete"
    if histogram["missing"] == len(checks):
        return "missing"
    if histogram["implemented"] >= max(1, len(checks) - 3) and histogram["missing"] <= 2:
        return "mostly_implemented"
    if histogram["implemented"] > 0:
        return "degraded"
    return "partial"
