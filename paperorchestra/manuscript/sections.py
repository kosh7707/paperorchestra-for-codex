from __future__ import annotations

import re
from typing import Any

from paperorchestra.manuscript.structure_titles import _canonical_generated_section_title

SECTION_RE = re.compile(r"\\section\*?\{([^}]+)\}")


def _normalize_section_title(title: str) -> str:
    return _canonical_generated_section_title(title)


def _section_bodies(latex: str) -> dict[str, str]:
    matches = list(SECTION_RE.finditer(latex))
    result: dict[str, str] = {}
    for idx, match in enumerate(matches):
        title = _normalize_section_title(match.group(1))
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else latex.find(r"\end{document}", start)
        if end == -1:
            end = len(latex)
        result[title] = latex[start:end]
    return result


def _substantive_text(text: str) -> str:
    stripped = re.sub(r"\\begin\{thebibliography\}.*", "", text, flags=re.DOTALL)
    stripped = re.sub(r"\\begin\{[^}]+\}|\\end\{[^}]+\}", " ", stripped)
    stripped = re.sub(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})?", " ", stripped)
    stripped = re.sub(r"[%].*", " ", stripped)
    stripped = re.sub(r"[^A-Za-z0-9가-힣]+", " ", stripped)
    return re.sub(r"\s+", " ", stripped).strip()


def _line_number(text: str, index: int) -> int:
    return text.count("\n", 0, max(0, index)) + 1


def _section_records(latex: str) -> list[dict[str, Any]]:
    matches = list(SECTION_RE.finditer(latex))
    records: list[dict[str, Any]] = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else latex.find(r"\end{document}", match.end())
        if end == -1:
            end = len(latex)
        title = match.group(1).strip()
        records.append(
            {
                "title": title,
                "normalized_title": _normalize_section_title(title),
                "start": start,
                "end": end,
                "line": _line_number(latex, start),
            }
        )
    return records


def _section_for_index(latex: str, index: int) -> dict[str, Any] | None:
    for section in _section_records(latex):
        if section["start"] <= index < section["end"]:
            return section
    return None
