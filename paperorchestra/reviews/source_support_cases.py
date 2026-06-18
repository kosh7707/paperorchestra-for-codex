from __future__ import annotations

import re
from typing import Any

from paperorchestra.manuscript.citations import CITE_COMMAND_RE
from paperorchestra.reviews.citation_sentences import _citation_review_body, _sentence_end, _sentence_start
from paperorchestra.reviews.citation_source_lean import _lean_source_payload


def _strip_cites(text: str) -> str:
    return re.sub(CITE_COMMAND_RE, "", text).replace("~", " ")


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _sentence_for_cite_in_paragraph(paragraph: str, cite_start: int, cite_end: int) -> str:
    start = _sentence_start(paragraph, cite_start)
    end = _sentence_end(paragraph, cite_end)
    return _collapse_ws(paragraph[start:end])


def _looks_like_section_heading(paragraph: str) -> bool:
    stripped = paragraph.strip()
    return bool(stripped and len(stripped) < 80 and stripped.endswith(".") and "\\cite" not in stripped)


def build_source_backed_citation_cases_from_latex(latex: str, citation_map: dict[str, Any]) -> list[dict[str, Any]]:
    body = _citation_review_body(latex)
    raw_paragraphs = [_collapse_ws(part) for part in re.split(r"\n\s*\n+", body) if _collapse_ws(part)]
    current_section = "Manuscript"
    paragraph_index = 0
    cases: list[dict[str, Any]] = []
    for paragraph in raw_paragraphs:
        if "\\cite" not in paragraph and _looks_like_section_heading(paragraph):
            current_section = paragraph.rstrip(".")
            continue
        if "\\cite" not in paragraph:
            continue
        paragraph_index += 1
        for match in CITE_COMMAND_RE.finditer(paragraph):
            raw_keys = [item.strip() for item in match.group(2).split(",") if item.strip()]
            anchor = _sentence_for_cite_in_paragraph(paragraph, match.start(), match.end())
            target = _collapse_ws(_strip_cites(anchor)).rstrip(".")
            for key in raw_keys:
                cases.append(
                    {
                        "id": f"C{len(cases) + 1}",
                        "key": key,
                        "loc": f"{current_section} ¶{paragraph_index}",
                        "paragraph": paragraph,
                        "anchor": anchor,
                        "target": target,
                        "source": _lean_source_payload(key, citation_map),
                    }
                )
    return cases
