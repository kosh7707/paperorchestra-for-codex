from __future__ import annotations

from typing import Any

from paperorchestra.feedback.operator_contexts.text import _normalized_context_text


def _integrity_problem_targets(citation_integrity_payload: dict[str, Any] | None) -> tuple[set[str], set[str]]:
    texts: set[str] = set()
    key_exclusions: set[str] = set()
    checks = citation_integrity_payload.get("checks") if isinstance(citation_integrity_payload, dict) else {}
    checks = checks if isinstance(checks, dict) else {}
    duplicate = checks.get("duplicate_support") if isinstance(checks.get("duplicate_support"), dict) else {}
    key_exclusions.update(str(key).strip() for key in duplicate.get("duplicate_keys") or [] if str(key).strip())
    density = checks.get("citation_density") if isinstance(checks.get("citation_density"), dict) else {}
    for item in density.get("bomb_sentences") or []:
        if not isinstance(item, dict):
            continue
        key_exclusions.update(str(key).strip() for key in item.get("citation_keys") or [] if str(key).strip())
        sentence = _normalized_context_text(item.get("sentence"))
        if sentence:
            texts.add(sentence)
    for key_set in density.get("bomb_paragraph_key_sets") or []:
        if isinstance(key_set, list):
            key_exclusions.update(str(key).strip() for key in key_set if str(key).strip())
    return texts, key_exclusions
