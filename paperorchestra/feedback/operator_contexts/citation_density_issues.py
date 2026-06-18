from __future__ import annotations

from typing import Any

from paperorchestra.feedback.operator_contexts.text import _truncate_context_text


def _citation_density_context(payload: dict[str, Any] | None, *, limit: int = 16) -> list[dict[str, Any]]:
    density = _citation_density(payload)
    result = _citation_bomb_sentence_context(density.get("bomb_sentences"), limit=limit)
    if len(result) >= limit:
        return result
    result.extend(_citation_bomb_paragraph_context(density.get("bomb_paragraph_key_sets"), limit=limit - len(result)))
    return result


def _citation_density(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
    return checks.get("citation_density") if isinstance(checks.get("citation_density"), dict) else {}


def _citation_bomb_sentence_context(items: Any, *, limit: int) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        keys = [str(key) for key in item.get("citation_keys") or [] if str(key).strip()]
        result.append(
            {
                "issue_type": "citation_bomb_sentence",
                "id": item.get("id"),
                "sentence": _truncate_context_text(item.get("sentence"), limit=900),
                "citation_keys": keys,
                "citation_count": len(keys),
                "suggested_fix": "Split the sentence, remove redundant references, or scope the claim while preserving directly supporting citations.",
            }
        )
        if len(result) >= limit:
            break
    return result


def _citation_bomb_paragraph_context(items: Any, *, limit: int) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, keys in enumerate(items or [], start=1):
        if not isinstance(keys, list):
            continue
        normalized = [str(key) for key in keys if str(key).strip()]
        result.append(
            {
                "issue_type": "citation_bomb_paragraph",
                "id": f"citation-bomb-paragraph-{index}",
                "citation_keys": normalized,
                "citation_count": len(normalized),
                "suggested_fix": "Distribute citations across claim-specific sentences or remove redundant references.",
            }
        )
        if len(result) >= limit:
            break
    return result
