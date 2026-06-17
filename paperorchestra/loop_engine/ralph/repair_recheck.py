from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from paperorchestra.core.io import write_json
from paperorchestra.core.session import artifact_path, load_session
from paperorchestra.loop_engine.quality.source_checks import _high_risk_claim_sweep
from paperorchestra.loop_engine.ralph.state import _read_json
from paperorchestra.manuscript.source_obligations import evaluate_source_obligations
from paperorchestra.reviews.citation_integrity import build_citation_integrity_audit


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

def _canonical_high_risk_baseline(
    cwd: str | Path | None,
    *,
    original_manuscript_hash: str | None,
) -> tuple[dict[str, Any] | None, str]:
    quality_path = artifact_path(cwd, "quality-eval.json")
    try:
        quality_eval = _read_json(quality_path)
    except Exception:
        return None, "quality_eval_missing"
    if not isinstance(quality_eval, dict):
        return None, "quality_eval_missing"
    expected_hash = str(original_manuscript_hash or "").strip()
    if expected_hash and not expected_hash.startswith("sha256:"):
        expected_hash = "sha256:" + expected_hash
    recorded_hash = str(quality_eval.get("manuscript_hash") or "").strip()
    if expected_hash and recorded_hash and recorded_hash != expected_hash:
        return None, "quality_eval_stale_ignored"
    if expected_hash and not recorded_hash:
        return None, "quality_eval_unbound_ignored"
    tiers = quality_eval.get("tiers") if isinstance(quality_eval.get("tiers"), dict) else {}
    tier2 = tiers.get("tier_2_claim_safety") if isinstance(tiers.get("tier_2_claim_safety"), dict) else {}
    checks = tier2.get("checks") if isinstance(tier2.get("checks"), dict) else {}
    sweep = checks.get("high_risk_claim_sweep") if isinstance(checks.get("high_risk_claim_sweep"), dict) else None
    if not isinstance(sweep, dict):
        return None, "quality_eval_high_risk_missing"
    return _high_risk_metrics(sweep), "quality_eval"

def _strictly_improves(before_count: int, after_count: int) -> bool:
    return before_count <= 0 or after_count < before_count

def _candidate_semantic_recheck(
    cwd: str | Path | None,
    *,
    claim_safety_issues: list[dict[str, Any]],
    quality_mode: str = "claim_safe",
    original_manuscript_hash: str | None = None,
) -> dict[str, Any]:
    citation_targeted = any(
        str(item.get("issue_type") or "").startswith("citation_bomb_")
        or item.get("issue_type") == "citation_duplicate_support"
        for item in claim_safety_issues
    )
    high_risk_targeted = any(item.get("issue_type") == "high_risk_uncited_claim" for item in claim_safety_issues)

    canonical_citation_path = artifact_path(cwd, "citation_integrity.audit.json")
    try:
        canonical_citation = _read_json(canonical_citation_path)
    except Exception:
        canonical_citation = {}
    citation_before = (
        _citation_integrity_metrics(canonical_citation)
        if isinstance(canonical_citation, dict) and canonical_citation
        else _citation_issue_metrics_from_packet(claim_safety_issues)
    )
    citation_after_payload = build_citation_integrity_audit(cwd, quality_mode=quality_mode)
    citation_after = _citation_integrity_metrics(citation_after_payload)
    citation_path = artifact_path(cwd, "citation-integrity.citation-repair.candidate.json")
    write_json(citation_path, citation_after_payload)

    high_risk_before, high_risk_baseline_source = _canonical_high_risk_baseline(
        cwd,
        original_manuscript_hash=original_manuscript_hash,
    )
    if high_risk_before is None:
        high_risk_before = _high_risk_issue_metrics_from_packet(claim_safety_issues)
        if high_risk_baseline_source in {"quality_eval_missing", "quality_eval_high_risk_missing"}:
            high_risk_baseline_source = "repair_packet"
    high_risk_after_payload = _high_risk_claim_sweep(load_session(cwd), evaluate_source_obligations(cwd))
    high_risk_after = _high_risk_metrics(high_risk_after_payload)
    high_risk_path = artifact_path(cwd, "high-risk-sweep.citation-repair.candidate.json")
    write_json(high_risk_path, high_risk_after_payload)

    citation_improved = (not citation_targeted) or _strictly_improves(
        int(citation_before.get("target_issue_count") or 0),
        int(citation_after.get("target_issue_count") or 0),
    )
    high_risk_improved = (not high_risk_targeted) or _strictly_improves(
        int(high_risk_before.get("item_count") or 0),
        int(high_risk_after.get("item_count") or 0),
    )
    status = "pass" if citation_improved and high_risk_improved else "fail"
    return {
        "status": status,
        "citation_integrity": {
            "targeted": citation_targeted,
            "path": str(citation_path),
            "sha256": _file_sha256(citation_path),
            "before": citation_before,
            "after": citation_after,
            "improved": citation_improved,
        },
        "high_risk_claim_sweep": {
            "targeted": high_risk_targeted,
            "baseline_source": high_risk_baseline_source,
            "path": str(high_risk_path),
            "sha256": _file_sha256(high_risk_path),
            "before": high_risk_before,
            "after": high_risk_after,
            "improved": high_risk_improved,
        },
    }
