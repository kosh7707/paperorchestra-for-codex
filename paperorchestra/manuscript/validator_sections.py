from __future__ import annotations

from paperorchestra.manuscript.sections import _normalize_section_title, _section_bodies, _substantive_text
from paperorchestra.manuscript.validation_types import ValidationIssue


def check_expected_section_substance(
    latex: str,
    expected_section_titles: list[str] | None,
    *,
    min_body_chars: int = 120,
) -> list[ValidationIssue]:
    if not expected_section_titles:
        return []
    bodies = _section_bodies(latex)
    missing: list[str] = []
    shallow: list[str] = []
    ignored = {"abstract", "appendix", "references", "bibliography"}
    for raw_title in expected_section_titles:
        title = _normalize_section_title(raw_title)
        if not title or title in ignored or title.startswith("appendix"):
            continue
        body = bodies.get(title)
        if body is None:
            missing.append(raw_title)
            continue
        if len(_substantive_text(body)) < min_body_chars:
            shallow.append(raw_title)
    issues = []
    if missing:
        issues.append(
            ValidationIssue(
                code="expected_section_missing",
                severity="error",
                message="Expected sections are missing from the manuscript: " + ", ".join(missing),
            )
        )
    if shallow:
        issues.append(
            ValidationIssue(
                code="expected_section_too_shallow",
                severity="error",
                message=f"Expected sections have too little substantive body text (<{min_body_chars} chars): "
                + ", ".join(shallow),
            )
        )
    return issues
