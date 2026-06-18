from __future__ import annotations

from typing import Any

from paperorchestra.feedback.operator_contexts.citation_protection_integrity_targets import _integrity_problem_targets
from paperorchestra.feedback.operator_contexts.citation_protection_review_targets import _review_problem_targets


def _protected_citation_target_context(
    citation_review_payload: dict[str, Any] | None,
    citation_integrity_payload: dict[str, Any] | None,
) -> dict[str, set[str]]:
    """Return exact citation-repair targets that should not be protected."""

    ids, texts = _review_problem_targets(citation_review_payload)
    integrity_texts, key_exclusions = _integrity_problem_targets(citation_integrity_payload)
    texts.update(integrity_texts)
    return {"ids": ids, "texts": texts, "key_exclusions": key_exclusions}
