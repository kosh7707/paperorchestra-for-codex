from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def _file_sha256(path: str | Path | None) -> str | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return None
    return hashlib.sha256(candidate.read_bytes()).hexdigest()


def _citation_integrity_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
    density = checks.get("citation_density") if isinstance(checks.get("citation_density"), dict) else {}
    duplicate = checks.get("duplicate_support") if isinstance(checks.get("duplicate_support"), dict) else {}
    bomb_sentence_count = len([item for item in density.get("bomb_sentences") or [] if isinstance(item, dict)])
    bomb_paragraph_count = len([item for item in density.get("bomb_paragraph_key_sets") or [] if isinstance(item, list)])
    duplicate_support_count = len([item for item in duplicate.get("duplicate_keys") or [] if str(item).strip()])
    total = bomb_sentence_count + bomb_paragraph_count + duplicate_support_count
    return {
        "status": str(payload.get("status") or "unknown"),
        "failing_codes": [str(code) for code in payload.get("failing_codes") or []],
        "citation_bomb_sentence_count": bomb_sentence_count,
        "citation_bomb_paragraph_count": bomb_paragraph_count,
        "duplicate_support_count": duplicate_support_count,
        "target_issue_count": total,
    }


def _citation_issue_metrics_from_packet(issues: list[dict[str, Any]]) -> dict[str, Any]:
    bomb_sentence_count = sum(1 for item in issues if item.get("issue_type") == "citation_bomb_sentence")
    bomb_paragraph_count = sum(1 for item in issues if item.get("issue_type") == "citation_bomb_paragraph")
    duplicate_support_count = sum(1 for item in issues if item.get("issue_type") == "citation_duplicate_support")
    total = bomb_sentence_count + bomb_paragraph_count + duplicate_support_count
    failing_codes: list[str] = []
    if bomb_sentence_count or bomb_paragraph_count:
        failing_codes.append("citation_bomb_detected")
    if duplicate_support_count:
        failing_codes.append("citation_duplicate_support")
    return {
        "status": "fail" if total else "pass",
        "failing_codes": failing_codes,
        "citation_bomb_sentence_count": bomb_sentence_count,
        "citation_bomb_paragraph_count": bomb_paragraph_count,
        "duplicate_support_count": duplicate_support_count,
        "target_issue_count": total,
    }


def _high_risk_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": str(payload.get("status") or "unknown"),
        "failing_codes": [str(code) for code in payload.get("failing_codes") or []],
        "item_count": int(payload.get("item_count") or len(payload.get("items") or [])),
    }


def _high_risk_issue_metrics_from_packet(issues: list[dict[str, Any]]) -> dict[str, Any]:
    count = sum(1 for item in issues if item.get("issue_type") == "high_risk_uncited_claim")
    return {
        "status": "fail" if count else "pass",
        "failing_codes": ["high_risk_uncited_claim"] if count else [],
        "item_count": count,
    }


def _strictly_improves(before_count: int, after_count: int) -> bool:
    return before_count <= 0 or after_count < before_count
