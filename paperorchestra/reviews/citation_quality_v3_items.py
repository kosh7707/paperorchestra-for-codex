from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.reviews.citation_quality_item_helpers import _sha256_text
from paperorchestra.reviews.citation_support_v3 import _v3_evidence_text_readable as _v3_evidence_is_readable


def _support_items_from_v3_cases(cases: Any, *, run_root: Path | None = None) -> list[dict[str, Any]]:
    if not isinstance(cases, list):
        return []
    items: list[dict[str, Any]] = []
    for case in cases:
        if not isinstance(case, dict):
            continue
        key = str(case.get("key") or "").strip()
        if not key:
            continue
        evidence = case.get("evidence") if isinstance(case.get("evidence"), dict) else {}
        evidence_readable = _v3_evidence_is_readable(evidence, run_root=run_root)
        verdict = str(case.get("verdict") or "human_needed").strip().lower() or "human_needed"
        items.append(
            {
                "id": str(case.get("id") or f"case:{_sha256_text(key)[:12]}"),
                "case_id": str(case.get("id") or f"case:{_sha256_text(key)[:12]}"),
                "citation_keys": [key],
                "support_status": _v3_support_status(verdict, evidence.get("status"), evidence_readable=evidence_readable),
                "evidence_status": str(evidence.get("status") or "missing").strip().lower() or "missing",
                "evidence_readable": evidence_readable,
                "review_schema": "citation-support-review/3",
                "verdict": verdict,
            }
        )
    return items


def _v3_support_status(verdict: Any, evidence_status: Any, *, evidence_readable: bool = False) -> str:
    status = str(evidence_status or "missing").strip().lower() or "missing"
    normalized = str(verdict or "human_needed").strip().lower() or "human_needed"
    if normalized == "pass":
        return "supported" if status in {"pdf", "html", "text"} and evidence_readable else "insufficient_evidence"
    if normalized == "weak":
        return "metadata_only"
    if normalized == "fail":
        return "unsupported"
    if normalized == "human_needed":
        return "insufficient_evidence"
    return "unknown"
