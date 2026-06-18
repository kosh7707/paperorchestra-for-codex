from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.loop_engine.ralph.repair_claim_safety_artifacts import (
    _citation_integrity_audit,
    _citation_support_review,
)
from paperorchestra.loop_engine.ralph.repair_issue_text import _truncate_issue_text


def _duplicate_support_repair_issues(cwd: str | Path | None, *, limit: int = 16, examples_per_key: int = 4) -> list[dict[str, Any]]:
    duplicate_keys = _duplicate_support_keys(cwd)
    if not duplicate_keys:
        return []
    support_items = _citation_support_items(cwd)
    issues: list[dict[str, Any]] = []
    for key in duplicate_keys:
        matching_items = _matching_support_items(key, support_items)
        issues.append(
            {
                "issue_type": "citation_duplicate_support",
                "citation_key": key,
                "occurrence_count": len(matching_items) or None,
                "affected_items": matching_items[:examples_per_key],
                "required_action": "remove or redistribute redundant repeated uses of this citation key; preserve the citation only where it directly supports a distinct claim and do not add bibliography keys",
            }
        )
        if len(issues) >= limit:
            break
    return issues


def _duplicate_support_keys(cwd: str | Path | None) -> list[str]:
    audit = _citation_integrity_audit(cwd)
    checks = audit.get("checks") if isinstance(audit.get("checks"), dict) else {}
    duplicate = checks.get("duplicate_support") if isinstance(checks.get("duplicate_support"), dict) else {}
    return [str(key).strip() for key in duplicate.get("duplicate_keys") or [] if str(key).strip()]


def _citation_support_items(cwd: str | Path | None) -> list[dict[str, Any]]:
    citation_review = _citation_support_review(cwd)
    items = citation_review.get("items") if isinstance(citation_review, dict) else []
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _matching_support_items(key: str, support_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matching_items: list[dict[str, Any]] = []
    for index, item in enumerate(support_items, start=1):
        keys = {str(candidate).strip() for candidate in item.get("citation_keys") or [] if str(candidate).strip()}
        if key not in keys:
            continue
        matching_items.append(
            {
                "id": str(item.get("id") or f"citation-support-{index}"),
                "sentence": _truncate_issue_text(item.get("sentence")),
                "support_status": str(item.get("support_status") or "unknown"),
                "claim_type": item.get("claim_type"),
            }
        )
    return matching_items
