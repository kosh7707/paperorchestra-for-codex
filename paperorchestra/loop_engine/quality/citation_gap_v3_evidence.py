from __future__ import annotations

from typing import Any


def v3_case_gap_evidence(case: dict[str, Any]) -> list[dict[str, Any]]:
    key = str(case.get("key") or "").strip()
    evidence: list[dict[str, Any]] = []
    for field in ("support_evidence", "verified_support_evidence"):
        evidence.extend(v3_case_evidence_entries(case.get(field), key=key, verified=True))
    resolution = case.get("resolution") if isinstance(case.get("resolution"), dict) else {}
    evidence.extend(v3_case_evidence_entries(resolution.get("support_evidence"), key=key, verified=True))
    for field in ("evidence_surfaces", "evidence_candidates"):
        evidence.extend(v3_case_evidence_entries(case.get(field), key=key, verified=False))
    return evidence


def v3_case_evidence_entries(value: Any, *, key: str, verified: bool) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [entry for raw in value if isinstance(raw, dict) for entry in [_v3_case_evidence_entry(raw, key=key, verified=verified)]]


def _v3_case_evidence_entry(entry: dict[str, Any], *, key: str, verified: bool) -> dict[str, Any]:
    supports_claim = entry.get("supports_claim") if entry.get("supports_claim") is not None else entry.get("supports")
    return {
        "citation_key": entry.get("citation_key") or key,
        "source_title": entry.get("source_title") or entry.get("title"),
        "url": entry.get("url") or entry.get("source_url"),
        "evidence_quote_or_summary": entry.get("evidence_quote_or_summary")
        or entry.get("quoted_or_paraphrased_support")
        or entry.get("quote_or_summary")
        or entry.get("summary"),
        "supports_claim": supports_claim if verified else False,
    }
