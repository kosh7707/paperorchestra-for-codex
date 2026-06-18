from __future__ import annotations

from typing import Any

from paperorchestra.manuscript.revision_action_taxonomy import _target_for_item, _target_for_section_title


def _iter_section_findings(section_review: dict[str, Any]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    sections = section_review.get("sections") if isinstance(section_review, dict) else []
    if not isinstance(sections, list):
        return findings
    for section in sections:
        if not isinstance(section, dict):
            continue
        title = str(section.get("section_title") or "").strip()
        fixes = section.get("required_fixes") if isinstance(section.get("required_fixes"), list) else []
        for idx, fix in enumerate(fixes, start=1):
            text = str(fix).strip()
            if text:
                findings.append(
                    {
                        "source": f"section_review.{title or 'unknown'}",
                        "source_index": str(idx),
                        "text": f"{title}: {text}" if title else text,
                        "target_area": _target_for_section_title(title),
                    }
                )
    return findings


def _iter_citation_findings(citation_review: dict[str, Any]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    items = citation_review.get("items") if isinstance(citation_review, dict) else []
    if not isinstance(items, list):
        return findings
    for item in items:
        if not isinstance(item, dict):
            continue
        status = str(item.get("support_status") or "").strip()
        risk = str(item.get("risk") or "").strip()
        if status == "supported" and risk == "low":
            continue
        sentence = str(item.get("sentence") or "").strip()
        fix = str(item.get("suggested_fix") or "Check citation support.").strip()
        citation_id = str(item.get("id") or len(findings) + 1)
        text = f"Citation support issue ({status or 'unknown'}, risk={risk or 'unknown'}): {fix} Claim: {sentence}"
        findings.append(
            {
                "source": "citation_support_review",
                "source_index": citation_id,
                "text": text,
                "target_area": _target_for_item(sentence + " " + fix),
                "action_type": "curate_and_verify_citations",
            }
        )
    return findings
