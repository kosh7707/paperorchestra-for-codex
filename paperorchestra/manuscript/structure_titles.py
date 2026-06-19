from __future__ import annotations

import re

_SECTION_TITLE_ALIASES = {
    "approach": "method",
    "architecture": "method",
    "evidence-grounded pipeline": "method",
    "framework": "method",
    "method": "method",
    "methodology": "method",
    "pipeline": "method",
    "pipeline design": "method",
    "proposed method": "method",
    "proposed approach": "method",
    "proposed system": "method",
    "system": "method",
    "system architecture": "method",
    "system design": "method",
    "triage pipeline": "method",
    "benchmark evaluation": "experiments",
    "benchmark setup": "experiments",
    "evaluation": "experiments",
    "evaluation design": "experiments",
    "evaluation setup": "experiments",
    "experiment design": "experiments",
    "experiment setup": "experiments",
    "experimental evaluation": "experiments",
    "experimental setup": "experiments",
    "implementation and results": "experiments",
    "implementation results": "experiments",
    "experiments": "experiments",
    "discussion and limitations": "discussion",
}


def _canonical_generated_section_title(title: str) -> str:
    raw = title.strip()
    if re.fullmatch(r"\\begin\{abstract\}.*?\\end\{abstract\}", raw, flags=re.DOTALL | re.IGNORECASE):
        raw = "abstract"
    elif re.fullmatch(r"\\+appendix\b.*", raw, flags=re.DOTALL | re.IGNORECASE):
        raw = "appendix"
    section_match = re.fullmatch(r"\\(?:sub)*section\*?\{(.+)\}", raw, flags=re.DOTALL)
    if section_match:
        raw = section_match.group(1).strip()
    normalized = re.sub(r"\s+", " ", raw.lower())
    return _SECTION_TITLE_ALIASES.get(normalized, normalized)
