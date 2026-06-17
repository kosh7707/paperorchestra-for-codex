from __future__ import annotations

import re
from typing import Any

from paperorchestra.feedback.packets import _sha256_bytes, _sha256_prefixed


def _section_texts(latex: str) -> dict[str, str]:
    matches = list(re.finditer(r"\\section\*?\{([^}]+)\}", latex))
    if not matches:
        return {"Whole manuscript": latex}
    sections: dict[str, str] = {"Whole manuscript": latex}
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(latex)
        title = re.sub(r"\s+", " ", match.group(1)).strip()
        sections[title] = latex[start:end]
    return sections


def _section_for_target(sections: dict[str, str], target: str | None) -> str:
    if not target:
        return sections.get("Whole manuscript", "")
    normalized_target = re.sub(r"[^a-z0-9]+", "", target.lower())
    for title, text in sections.items():
        normalized_title = re.sub(r"[^a-z0-9]+", "", title.lower())
        if normalized_title and (normalized_title in normalized_target or normalized_target in normalized_title):
            return text
    return sections.get("Whole manuscript", "")


def _issue_terms(issue: dict[str, Any]) -> list[str]:
    text = f"{issue.get('rationale') or ''} {issue.get('suggested_action') or ''}"
    stop = {
        "the",
        "and",
        "that",
        "with",
        "into",
        "this",
        "from",
        "after",
        "before",
        "without",
        "should",
        "must",
        "section",
        "paper",
        "manuscript",
        "write",
        "rewrite",
        "add",
    }
    terms = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{4,}", text.lower()):
        if token not in stop and token not in terms:
            terms.append(token)
    return terms[:12]


def _issue_incorporation_detailed(
    issues: list[dict[str, Any]],
    before_text: str,
    after_text: str,
    *,
    blocking_codes: list[str],
) -> list[dict[str, Any]]:
    before_sections = _section_texts(before_text)
    after_sections = _section_texts(after_text)
    results: list[dict[str, Any]] = []
    for issue in issues:
        before_section = _section_for_target(before_sections, str(issue.get("target_section") or ""))
        after_section = _section_for_target(after_sections, str(issue.get("target_section") or ""))
        changed = before_section != after_section
        terms = _issue_terms(issue)
        matched_terms = [term for term in terms if term in after_section.lower()]
        if any(str(code).startswith(("unsupported", "numeric_grounding", "citation_coverage", "unknown_citation")) for code in blocking_codes):
            status = "blocked_by_claim_safety"
        elif changed and (matched_terms or not terms):
            status = "reflected"
        elif changed:
            status = "partially_reflected"
        elif blocking_codes:
            status = "needs_author_decision"
        else:
            status = "not_reflected"
        evidence = (
            "target section changed"
            if changed
            else "target section did not change"
        )
        results.append(
            {
                "issue_id": issue.get("id"),
                "status": status,
                "target_section": issue.get("target_section"),
                "owner_category": issue.get("owner_category"),
                "before_section_sha256": _sha256_prefixed(_sha256_bytes(before_section.encode("utf-8"))),
                "after_section_sha256": _sha256_prefixed(_sha256_bytes(after_section.encode("utf-8"))),
                "changed": changed,
                "matched_terms": matched_terms,
                "blocking_codes": blocking_codes,
                "evidence": evidence,
            }
        )
    return results


