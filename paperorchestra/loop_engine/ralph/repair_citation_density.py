from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.loop_engine.ralph.repair_claim_safety_artifacts import _citation_integrity_audit
from paperorchestra.loop_engine.ralph.repair_issue_text import _truncate_issue_text


def _citation_density_repair_issues(cwd: str | Path | None, *, limit: int = 16) -> list[dict[str, Any]]:
    density = _citation_density_check(cwd)
    issues = _citation_bomb_sentence_issues(density.get("bomb_sentences"), limit=limit)
    if len(issues) >= limit:
        return issues
    issues.extend(_citation_bomb_paragraph_issues(density.get("bomb_paragraph_key_sets"), limit=limit - len(issues)))
    return issues


def _citation_density_check(cwd: str | Path | None) -> dict[str, Any]:
    audit = _citation_integrity_audit(cwd)
    checks = audit.get("checks") if isinstance(audit.get("checks"), dict) else {}
    density = checks.get("citation_density") if isinstance(checks.get("citation_density"), dict) else {}
    return density


def _citation_bomb_sentence_issues(items: Any, *, limit: int) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for item in items or []:
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
            break
    return issues


def _citation_bomb_paragraph_issues(items: Any, *, limit: int) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for index, keys in enumerate(items or [], start=1):
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
