from __future__ import annotations

from typing import Any

from paperorchestra.reviews.citation_quality_tokens import _tokens_for_fields

_HIGH_CRITICAL_TOKENS = {
    "critical",
    "high",
    "root",
    "central_support",
    "numeric",
    "comparative",
    "security",
    "novelty",
    "causal",
    "benchmark",
    "result",
}
_EXTERNAL_REQUIRED_SOURCE_TYPES = {
    "external_literature",
    "standard",
    "benchmark_reference",
    "prior_work",
}
_NONCRITICAL_TOKENS = {"background", "local", "optional", "low"}
_UNSUPPORTED_STATUSES = {"unsupported", "contradicted", "metadata_only", "insufficient_evidence"}


def _is_critical_key(
    key: str,
    support_items: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    roles: set[str],
    *,
    mode: str,
    metadata_problem: bool,
) -> bool:
    if any(item.get("critical") is True for item in support_items):
        return True
    for item in support_items:
        if _tokens_for_fields(item, ("claim_type", "criticality", "citation_role", "support_role")) & _HIGH_CRITICAL_TOKENS:
            return True
    for claim in claims:
        if claim.get("required") is True or claim.get("citation_required") is True:
            return True
        if str(claim.get("required_source_type") or "").strip().lower() in _EXTERNAL_REQUIRED_SOURCE_TYPES:
            return True
        if _tokens_for_fields(claim, ("claim_type", "criticality", "graph_role")) & _HIGH_CRITICAL_TOKENS:
            return True
    if roles & _HIGH_CRITICAL_TOKENS:
        return True
    if mode == "claim_safe" and metadata_problem and not claims and not support_items:
        return True
    return False


def _is_explicitly_noncritical(claims: list[dict[str, Any]], roles: set[str]) -> bool:
    if roles & _HIGH_CRITICAL_TOKENS:
        return False
    if roles & _NONCRITICAL_TOKENS:
        return True
    if not claims:
        return False
    for claim in claims:
        if claim.get("required") is True or claim.get("citation_required") is True:
            return False
        if str(claim.get("required_source_type") or "").strip().lower() in _EXTERNAL_REQUIRED_SOURCE_TYPES:
            return False
        if _tokens_for_fields(claim, ("claim_type", "criticality", "graph_role")) & _HIGH_CRITICAL_TOKENS:
            return False
    return any(_tokens_for_fields(claim, ("claim_type", "criticality", "graph_role")) & _NONCRITICAL_TOKENS for claim in claims)
