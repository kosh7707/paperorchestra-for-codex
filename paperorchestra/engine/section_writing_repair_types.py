from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SectionRepairResult:
    latex: str
    validation_issues: list[Any]
    blocking_issues: list[Any]
    lane_notes: list[str]
    lane_type: str
    fallback_used: bool
