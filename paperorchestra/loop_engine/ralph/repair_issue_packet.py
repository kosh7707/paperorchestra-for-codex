from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.ralph.repair_claim_safety_issues import (
    _claim_safety_repair_issues,
    _citation_density_repair_issues,
    _duplicate_support_repair_issues,
    _high_risk_repair_issues,
    _truncate_issue_text,
)
from paperorchestra.loop_engine.ralph.repair_source_obligations import _source_obligation_repair_context
from paperorchestra.loop_engine.ralph.state import NON_SUPPORTED_CITATION_STATUSES


def _non_supported_citation_items(citation_review: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in citation_review.get("items") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("support_status") or "") in NON_SUPPORTED_CITATION_STATUSES:
            result.append(item)
    return result


__all__ = [
    "_claim_safety_repair_issues",
    "_citation_density_repair_issues",
    "_duplicate_support_repair_issues",
    "_high_risk_repair_issues",
    "_non_supported_citation_items",
    "_source_obligation_repair_context",
    "_truncate_issue_text",
]
