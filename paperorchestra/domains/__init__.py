from __future__ import annotations

import os

from .base import DomainProfile
from .generic import GENERIC

_DOMAINS = {
    GENERIC.name: GENERIC,
}


def _normalize_domain_name(name: str) -> str:
    selected = name.strip().lower().replace("-", "_")
    if not selected:
        raise ValueError("Domain name must be non-empty.")
    return selected


def get_domain(name: str | None = None) -> DomainProfile:
    raw_name = name if name is not None else os.environ.get("PAPERO_DOMAIN")
    selected = _normalize_domain_name(raw_name or "generic")
    if selected in _DOMAINS:
        return _DOMAINS[selected]
    available = ", ".join(available_domains())
    raise ValueError(f"Unknown PaperOrchestra domain profile {selected!r}. Available profiles: {available}.")


def register_domain(profile: DomainProfile, *, replace: bool = False) -> DomainProfile:
    """Register an external domain profile before importing domain-cached modules.

    Several deterministic gates cache fields from ``get_domain()`` at module
    import time for speed and reproducibility.  Plugins should therefore call
    this function, set ``PAPERO_DOMAIN`` or pass the registered name explicitly,
    and only then import modules such as ``pipeline``, ``critics``, or
    ``source_obligations``.
    """

    if not isinstance(profile, DomainProfile):
        raise TypeError("register_domain() expects a DomainProfile instance.")
    selected = _normalize_domain_name(profile.name)
    if selected in _DOMAINS and not replace:
        raise ValueError(f"Domain profile {selected!r} is already registered; pass replace=True to override it.")
    _DOMAINS[selected] = profile
    return profile


def available_domains() -> tuple[str, ...]:
    return tuple(sorted(_DOMAINS))


def detect_domain_for_text(text: str, fallback: str | None = None) -> DomainProfile:
    """Return the active deterministic writing profile for manuscript text.

    Public PaperOrchestra is intentionally domain-neutral.  Project-specific
    vocabularies should live in external/private material packs or plugins, not
    in the bundled engine.
    """
    return get_domain(fallback)


__all__ = ["DomainProfile", "GENERIC", "available_domains", "detect_domain_for_text", "get_domain", "register_domain"]
