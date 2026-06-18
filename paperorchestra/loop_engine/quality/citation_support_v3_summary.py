from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_V3_SUMMARY_KEYS = ("pass", "weak", "fail", "human_needed")


@dataclass(frozen=True)
class CitationSupportV3Summary:
    counts: dict[str, int]
    invalid_verdicts: list[str]


def summarize_v3_cases(cases: list[dict[str, Any]]) -> CitationSupportV3Summary:
    summary = {key: 0 for key in _V3_SUMMARY_KEYS}
    invalid_verdicts: list[str] = []
    for case in cases:
        verdict = str(case.get("verdict") or "human_needed")
        if verdict not in summary:
            invalid_verdicts.append(verdict)
            verdict = "human_needed"
        summary[verdict] += 1
    return CitationSupportV3Summary(counts=summary, invalid_verdicts=invalid_verdicts)
