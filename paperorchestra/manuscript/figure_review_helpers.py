from __future__ import annotations

import re

from paperorchestra.manuscript.figure_patterns import FIGURE_ENV_RE, LABEL_RE, REF_RE
from paperorchestra.manuscript.figure_review_types import FigurePlacementWarning


def source_figure_labels(source_latex: str | None) -> set[str]:
    if not source_latex:
        return set()
    labels: set[str] = set()
    for match in FIGURE_ENV_RE.finditer(source_latex):
        label_match = LABEL_RE.search(match.group(3))
        if label_match:
            labels.add(label_match.group(1))
    return labels


def figure_source_origin(block: str, label: str | None, source_labels: set[str], *, prefix: str = "") -> str:
    if "PaperOrchestra:auto-repaired" in block or "PaperOrchestra:auto-repaired" in prefix:
        return "auto_repaired"
    if label and label in source_labels:
        return "source_preserved"
    return "model_written"


def compact_context(text: str, *, start: int, end: int, limit: int = 500) -> str:
    left = max(0, start - limit // 2)
    right = min(len(text), end + limit // 2)
    snippet = text[left:right]
    snippet = re.sub(r"\s+", " ", snippet).strip()
    return snippet[:limit]


def figure_ref_labels(match: re.Match[str]) -> set[str]:
    return {part.strip() for part in match.group(1).split(",") if part.strip()}


def figure_warning(
    code: str,
    *,
    label: str | None,
    detail: str,
) -> FigurePlacementWarning:
    subject = label or "<unlabeled>"
    return FigurePlacementWarning(code=code, message=f"{subject}: {detail}")


def bibliography_start_index(latex: str) -> int:
    bibliography_start = latex.find(r"\bibliographystyle")
    if bibliography_start == -1:
        bibliography_start = latex.find(r"\bibliography")
    return bibliography_start


def figure_references(latex: str, *, label: str | None, figure_start: int, figure_end: int) -> list[re.Match[str]]:
    if not label:
        return []
    return [
        match
        for match in REF_RE.finditer(latex)
        if label in figure_ref_labels(match) and not (figure_start <= match.start() < figure_end)
    ]
