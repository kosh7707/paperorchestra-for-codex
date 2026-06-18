from __future__ import annotations

from typing import Any

from paperorchestra.reviews.citation_evidence import citation_item_has_valid_supporting_evidence

AUTHOR_JUDGMENT_AUTHORITY_CLASSES = {"author_judgment", "operator_judgment", "domain_judgment", "author_feedback"}
MANUAL_SUPPORT_STATUSES = {"needs_manual_check", "manual_check"}
AUTHOR_JUDGMENT_FLAGS = {
    "requires_author_judgment",
    "author_judgment_required",
    "requires_operator_judgment",
    "operator_judgment_required",
    "operator_judgment",
    "domain_judgment",
    "author_feedback",
}


def payload_unavailable_gap_classification() -> dict[str, Any]:
    return {
        "machine_solvable_count": 0,
        "machine_research_needed_count": 0,
        "manual_author_judgment_count": 1,
        "author_judgment_count": 1,
        "payload_unavailable": True,
    }


def no_gap_items_classification(*, v3_payload: bool) -> dict[str, Any]:
    manual_count = 0 if v3_payload else 1
    return {
        "machine_solvable_count": 0,
        "machine_research_needed_count": 0,
        "manual_author_judgment_count": manual_count,
        "author_judgment_count": manual_count,
        "payload_unavailable": not v3_payload,
    }


def classify_citation_support_gap_items(items: list[dict[str, Any]]) -> dict[str, Any]:
    machine_solvable_count = 0
    machine_research_needed_count = 0
    manual_author_judgment_count = 0
    weak_author_marker_count = 0
    for item in items:
        classification = _classify_gap_item(item)
        if classification == "machine_solvable":
            machine_solvable_count += 1
        elif classification == "machine_research_needed":
            machine_research_needed_count += 1
        elif classification == "manual_author_judgment":
            manual_author_judgment_count += 1
        elif classification == "weak_author_marker":
            weak_author_marker_count += 1
    return {
        "machine_solvable_count": machine_solvable_count,
        "machine_research_needed_count": machine_research_needed_count,
        "manual_author_judgment_count": manual_author_judgment_count,
        "weak_author_marker_count": weak_author_marker_count,
        "author_judgment_count": manual_author_judgment_count,
        "payload_unavailable": False,
    }


def _classify_gap_item(item: dict[str, Any]) -> str | None:
    status = str(item.get("support_status") or "").strip()
    suggested_fix = str(item.get("suggested_fix") or item.get("suggested_action") or "").strip()
    explicit_author_judgment = _requires_author_judgment(item)
    if suggested_fix and citation_item_has_valid_supporting_evidence(item) and not explicit_author_judgment:
        return "machine_solvable"
    if suggested_fix and _has_concrete_unbound_evidence_surface(item) and not explicit_author_judgment:
        return "machine_research_needed"
    if status in MANUAL_SUPPORT_STATUSES:
        return "manual_author_judgment"
    if explicit_author_judgment:
        return "weak_author_marker"
    return None


def _requires_author_judgment(item: dict[str, Any]) -> bool:
    authority_class = str(item.get("authority_class") or "").strip().lower()
    flags = _normalized_flags(item.get("flags"))
    return (
        item.get("requires_author_judgment") is True
        or item.get("author_judgment_required") is True
        or item.get("requires_operator_judgment") is True
        or item.get("operator_judgment_required") is True
        or authority_class in AUTHOR_JUDGMENT_AUTHORITY_CLASSES
        or bool(flags & AUTHOR_JUDGMENT_FLAGS)
    )


def _normalized_flags(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {str(flag).strip().lower() for flag in value if str(flag).strip()}


def _has_concrete_unbound_evidence_surface(item: dict[str, Any]) -> bool:
    evidence = item.get("evidence")
    if not isinstance(evidence, list):
        return False
    for entry in evidence:
        if not isinstance(entry, dict):
            continue
        locator = str(
            entry.get("url") or entry.get("source_url") or entry.get("source_title") or entry.get("title") or ""
        ).strip()
        support_text = str(
            entry.get("evidence_quote_or_summary")
            or entry.get("quoted_or_paraphrased_support")
            or entry.get("quote_or_summary")
            or entry.get("summary")
            or ""
        ).strip()
        if locator and support_text:
            return True
    return False
