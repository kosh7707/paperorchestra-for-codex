from __future__ import annotations

from paperorchestra.research.s2_client import SemanticScholarClient

_DEFAULT_CLIENT: SemanticScholarClient | None = None


def get_default_semantic_scholar_client() -> SemanticScholarClient:
    global _DEFAULT_CLIENT
    if _DEFAULT_CLIENT is None:
        _DEFAULT_CLIENT = SemanticScholarClient()
    return _DEFAULT_CLIENT


def reset_default_semantic_scholar_client() -> None:
    global _DEFAULT_CLIENT
    _DEFAULT_CLIENT = None
