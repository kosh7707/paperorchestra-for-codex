from __future__ import annotations

import os

from .base import DomainProfile
from .generic import GENERIC

_DOMAINS = {
    GENERIC.name: GENERIC,
}


def get_domain(name: str | None = None) -> DomainProfile:
    selected = (name or os.environ.get("PAPERO_DOMAIN") or "generic").strip().lower().replace("-", "_")
    if selected in _DOMAINS:
        return _DOMAINS[selected]
    return GENERIC


def available_domains() -> tuple[str, ...]:
    return tuple(sorted(_DOMAINS))


def detect_domain_for_text(text: str, fallback: str | None = None) -> DomainProfile:
    """Return the active deterministic writing profile for manuscript text.

    Public PaperOrchestra is intentionally domain-neutral.  Project-specific
    vocabularies should live in external/private material packs or plugins, not
    in the bundled engine.
    """
    return get_domain(fallback)


__all__ = ["DomainProfile", "GENERIC", "available_domains", "detect_domain_for_text", "get_domain"]
