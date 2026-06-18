from __future__ import annotations

import re
from typing import Any

from paperorchestra.manuscript.citations import canonical_citation_map
from paperorchestra.manuscript.narrative_sources import _planning_source_text, _salient_terms


def _coverage_groups_for_method(source_text: str) -> list[list[str]]:
    groups: list[list[str]] = [["method"], ["construction"]]
    for term in _salient_terms(source_text, limit=4):
        if term not in {"method", "construction"}:
            groups.append([term])
    return groups


def _coverage_groups_for_benchmark(source_text: str) -> list[list[str]]:
    groups: list[list[str]] = [["benchmark", "measurement"], ["implementation", "profile"], ["message", "size"]]
    existing = {term for group in groups for term in group}
    for term in _salient_terms(_planning_source_text(source_text), limit=2):
        if term not in existing:
            groups.append([term])
    return groups


def _first_key(citation_map: dict[str, Any]) -> str | None:
    for key in canonical_citation_map(citation_map):
        if isinstance(key, str) and key.strip():
            return key
    return None


def _log_contains_result_claim(log_text: str) -> bool:
    if not log_text.strip():
        return False
    if re.search(r"\d+(?:\.\d+)\s*(?:x|×|%|ms|s|jobs/s|qps)?|\d+\s*(?:x|×|%|ms|s|jobs/s|qps)", log_text):
        return True
    result_words = r"\b(report|reports|show|shows|improve|outperform|faster|slower|accuracy|latency|throughput|runtime|speedup|ablation|result)\b"
    return bool(re.search(result_words, log_text, re.I))
