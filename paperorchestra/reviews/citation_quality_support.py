from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from paperorchestra.reviews.citation_quality_public import _default_public_failure_message


def _support_items(payload: Any, *, run_root: Path | None = None) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and payload.get("schema") == "citation-support-review/3":
        return _support_items_from_v3_cases(payload.get("cases"), run_root=run_root)
    items = payload.get("items") if isinstance(payload, dict) else None
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


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


def _public_case_id(support_items: list[dict[str, Any]], claims: list[dict[str, Any]]) -> str | None:
    for item in support_items:
        case_id = item.get("case_id") or item.get("id")
        if case_id:
            return str(case_id)
    return _first_claim_id(claims)


def _support_groups_for_quality_items(support_items: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    if not support_items:
        return [[]]
    v3_items = [item for item in support_items if item.get("review_schema") == "citation-support-review/3"]
    if not v3_items:
        return [support_items]
    groups = [[item] for item in v3_items]
    legacy_items = [item for item in support_items if item.get("review_schema") != "citation-support-review/3"]
    if legacy_items:
        groups.append(legacy_items)
    return groups


def _quality_item_id(key: str, support_items: list[dict[str, Any]], *, group_index: int) -> str:
    for item in support_items:
        if item.get("review_schema") == "citation-support-review/3":
            case_id = str(item.get("case_id") or item.get("id") or "").strip()
            basis = f"{key}:v3:{case_id}:{group_index}"
            return f"redacted-citation-item:{_sha256_text(basis)[:12]}"
    return f"redacted-citation-item:{_sha256_text(key)[:12]}"


def _public_failure_code(support_items: list[dict[str, Any]], key_failures: list[str]) -> str | None:
    for item in support_items:
        if item.get("review_schema") == "citation-support-review/3" and item.get("verdict") == "human_needed":
            return "human_needed"
    return str(key_failures[0]) if key_failures else None


def _public_failure_message(support_items: list[dict[str, Any]], key_failures: list[str]) -> str | None:
    code = _public_failure_code(support_items, key_failures)
    return _default_public_failure_message(code) if code else None


def _v3_evidence_is_readable(evidence: dict[str, Any], *, run_root: Path | None) -> bool:
    status = str(evidence.get("status") or "missing").strip().lower() or "missing"
    text_value = evidence.get("text")
    path_value = evidence.get("path")
    candidates: list[Path] = []
    for value in [text_value, path_value if status == "text" else None]:
        if not isinstance(value, str) or not value.strip():
            continue
        raw = Path(value)
        candidates.append(raw if raw.is_absolute() or run_root is None else run_root / raw)
    for candidate in candidates:
        try:
            if candidate.exists() and candidate.is_file() and candidate.stat().st_size > 0:
                return True
        except OSError:
            continue
    return False


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


def _support_by_key(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        for key in item.get("citation_keys") or []:
            normalized = str(key).strip()
            if normalized:
                result.setdefault(normalized, []).append(item)
    return result


def _worst_support_status(items: list[dict[str, Any]]) -> str:
    if not items:
        return "unknown"
    order = ["contradicted", "unsupported", "metadata_only", "insufficient_evidence", "unknown", "supported"]
    statuses = {str(item.get("support_status") or "unknown").strip().lower() or "unknown" for item in items}
    for status in order:
        if status in statuses:
            return status
    return sorted(statuses)[0]


def _first_claim_id(claims: list[dict[str, Any]]) -> str | None:
    for claim in claims:
        claim_id = claim.get("id") or claim.get("claim_id")
        if claim_id:
            return str(claim_id)
    return None


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()
