from __future__ import annotations

import re
from typing import Any

from paperorchestra.research.matching import title_match_ratio


def normalize_eval_title(text: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in text).split())

def _compact_eval_title(text: str) -> str:
    return "".join(ch.lower() for ch in text if ch.isalnum())

def _title_matches_reference(reference_title: str, generated_title: str) -> tuple[bool, float, str]:
    reference_normalized = normalize_eval_title(reference_title)
    generated_normalized = normalize_eval_title(generated_title)
    if reference_normalized == generated_normalized:
        return True, 100.0, "exact"
    reference_compact = _compact_eval_title(reference_title)
    generated_compact = _compact_eval_title(generated_title)
    compact_safe = (
        min(len(reference_normalized.split()), len(generated_normalized.split())) == 1
        or
        min(len(reference_normalized.split()), len(generated_normalized.split())) >= 3
        or min(len(reference_compact), len(generated_compact)) >= 18
    )
    if compact_safe and generated_compact and reference_compact and (
        generated_compact in reference_compact or reference_compact in generated_compact
    ):
        return True, 95.0, "compact"
    score = title_match_ratio(reference_title, generated_title)
    if score >= 70.0:
        return True, score, "fuzzy"
    return False, score, ""


def _extract_metric_range(text: str, metric_label: str) -> tuple[float, float] | None:
    patterns = [
        re.compile(
            rf"(\d+(?:\.\d+)?)%\s*(?:–|-|to)\s*(\d+(?:\.\d+)?)%\s+in\s+{re.escape(metric_label)}",
            re.IGNORECASE,
        ),
        re.compile(
            rf"{re.escape(metric_label)}.{{0,80}}?(\d+(?:\.\d+)?)%\s*(?:–|-|to)\s*(\d+(?:\.\d+)?)%",
            re.IGNORECASE | re.DOTALL,
        ),
    ]
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return float(match.group(1)), float(match.group(2))
    return None

def parse_reported_margin_ranges(text: str) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for key, label in [
        ("literature_review_quality", "literature review quality"),
        ("overall_manuscript_quality", "overall manuscript quality"),
    ]:
        margin = _extract_metric_range(text, label)
        if margin is not None:
            results[key] = {
                "min": margin[0],
                "max": margin[1],
                "unit": "absolute_win_rate_margin_percent",
                "source_excerpt": label,
            }
    return results
