from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.session import artifact_path
from paperorchestra.manuscript.source_obligations import evaluate_source_obligations, source_obligations_path
from paperorchestra.loop_engine.ralph.state import NON_SUPPORTED_CITATION_STATUSES, _read_json


def _non_supported_citation_items(citation_review: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in citation_review.get("items") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("support_status") or "") in NON_SUPPORTED_CITATION_STATUSES:
            result.append(item)
    return result

def _truncate_issue_text(value: Any, *, limit: int = 900) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."

def _citation_density_repair_issues(cwd: str | Path | None, *, limit: int = 16) -> list[dict[str, Any]]:
    audit_path = artifact_path(cwd, "citation_integrity.audit.json")
    try:
        audit = _read_json(audit_path)
    except Exception:
        return []
    if not isinstance(audit, dict):
        return []
    checks = audit.get("checks") if isinstance(audit.get("checks"), dict) else {}
    density = checks.get("citation_density") if isinstance(checks.get("citation_density"), dict) else {}
    issues: list[dict[str, Any]] = []
    for item in density.get("bomb_sentences") or []:
        if not isinstance(item, dict):
            continue
        keys = [str(key) for key in item.get("citation_keys") or [] if str(key).strip()]
        issues.append(
            {
                "issue_type": "citation_bomb_sentence",
                "id": item.get("id"),
                "sentence": _truncate_issue_text(item.get("sentence")),
                "citation_keys": keys,
                "citation_count": len(keys),
                "required_action": "split the sentence, remove redundant references, or scope the claim without adding bibliography keys",
            }
        )
        if len(issues) >= limit:
            return issues
    for index, keys in enumerate(density.get("bomb_paragraph_key_sets") or [], start=1):
        if not isinstance(keys, list):
            continue
        normalized = [str(key) for key in keys if str(key).strip()]
        issues.append(
            {
                "issue_type": "citation_bomb_paragraph",
                "id": f"citation-bomb-paragraph-{index}",
                "citation_keys": normalized,
                "citation_count": len(normalized),
                "required_action": "distribute citations across claim-specific sentences or remove redundant references",
            }
        )
        if len(issues) >= limit:
            break
    return issues

def _duplicate_support_repair_issues(cwd: str | Path | None, *, limit: int = 16, examples_per_key: int = 4) -> list[dict[str, Any]]:
    audit_path = artifact_path(cwd, "citation_integrity.audit.json")
    try:
        audit = _read_json(audit_path)
    except Exception:
        return []
    if not isinstance(audit, dict):
        return []
    checks = audit.get("checks") if isinstance(audit.get("checks"), dict) else {}
    duplicate = checks.get("duplicate_support") if isinstance(checks.get("duplicate_support"), dict) else {}
    duplicate_keys = [str(key).strip() for key in duplicate.get("duplicate_keys") or [] if str(key).strip()]
    if not duplicate_keys:
        return []
    review_path = artifact_path(cwd, "citation_support_review.json")
    try:
        citation_review = _read_json(review_path)
    except Exception:
        citation_review = {}
    items = citation_review.get("items") if isinstance(citation_review, dict) else []
    support_items = [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []
    issues: list[dict[str, Any]] = []
    for key in duplicate_keys:
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

def _high_risk_repair_issues(cwd: str | Path | None, *, limit: int = 16) -> list[dict[str, Any]]:
    quality_path = artifact_path(cwd, "quality-eval.json")
    try:
        quality_eval = _read_json(quality_path)
    except Exception:
        return []
    if not isinstance(quality_eval, dict):
        return []
    tiers = quality_eval.get("tiers") if isinstance(quality_eval.get("tiers"), dict) else {}
    tier2 = tiers.get("tier_2_claim_safety") if isinstance(tiers.get("tier_2_claim_safety"), dict) else {}
    checks = tier2.get("checks") if isinstance(tier2.get("checks"), dict) else {}
    sweep = checks.get("high_risk_claim_sweep") if isinstance(checks.get("high_risk_claim_sweep"), dict) else {}
    issues: list[dict[str, Any]] = []
    for item in sweep.get("items") or []:
        if not isinstance(item, dict):
            continue
        issues.append(
            {
                "issue_type": "high_risk_uncited_claim",
                "line": item.get("line"),
                "sentence": _truncate_issue_text(item.get("sentence")),
                "reason": _truncate_issue_text(item.get("reason"), limit=500),
                "required_action": "ground with existing verified evidence, scope as a limitation/author-material claim, or delete",
            }
        )
        if len(issues) >= limit:
            break
    return issues

def _claim_safety_repair_issues(cwd: str | Path | None) -> list[dict[str, Any]]:
    return _citation_density_repair_issues(cwd) + _duplicate_support_repair_issues(cwd) + _high_risk_repair_issues(cwd)

def _source_obligation_repair_context(cwd: str | Path | None, *, limit: int = 48) -> dict[str, Any]:
    try:
        trust_report = evaluate_source_obligations(cwd)
    except Exception as exc:
        return {"available": False, "reason": "source_obligation_trust_check_error", "error_type": type(exc).__name__}
    trust_failing_codes = {
        str(code)
        for code in trust_report.get("failing_codes") or []
        if str(code).strip()
    } if isinstance(trust_report, dict) else {"source_obligations_missing"}
    untrusted_codes = {
        "source_obligations_missing",
        "source_obligations_stale",
        "source_obligations_legacy_untrusted",
    }
    if trust_failing_codes & untrusted_codes:
        return {
            "available": False,
            "reason": sorted(trust_failing_codes & untrusted_codes)[0],
            "failing_codes": sorted(trust_failing_codes),
        }
    try:
        path = source_obligations_path(cwd)
        payload = _read_json(path)
    except Exception:
        return {"available": False}
    if not isinstance(payload, dict):
        return {"available": False}
    obligations: list[dict[str, Any]] = []
    for obligation in payload.get("obligations") or []:
        if not isinstance(obligation, dict):
            continue
        obligations.append(
            {
                "id": obligation.get("id"),
                "type": obligation.get("type"),
                "expected_manuscript_area": obligation.get("expected_manuscript_area"),
                "required_terms": obligation.get("required_terms") or [],
                "numeric_tokens": obligation.get("numeric_tokens") or [],
                "excerpt_preview": _truncate_issue_text(obligation.get("excerpt_preview"), limit=360),
            }
        )
        if len(obligations) >= limit:
            break
    return {
        "available": True,
        "path": str(path),
        "obligation_count": len(payload.get("obligations") or []),
        "included_obligation_count": len(obligations),
        "obligations": obligations,
    }
