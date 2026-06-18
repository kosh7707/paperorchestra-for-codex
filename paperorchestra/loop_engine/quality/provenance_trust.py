from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.quality.provenance_evidence import (
    _append_citation_provenance_evidence,
    _base_provenance_evidence,
)


def _provenance_trust(reproducibility: dict[str, Any]) -> dict[str, Any]:
    citation_live_provenance = reproducibility.get("citation_live_provenance")
    citation_registry_live_verified_count = 0
    if isinstance(citation_live_provenance, dict):
        citation_registry_live_verified_count = int(citation_live_provenance.get("live_verified_count") or 0)
    citation_registry_verification_invoked = bool(reproducibility.get("verification_invoked"))
    citation_support_review_live = bool(reproducibility.get("citation_support_review_live"))
    semantic_scholar_required = bool(reproducibility.get("semantic_scholar_required"))

    mock_evidence, mixed_evidence = _base_provenance_evidence(reproducibility)
    _append_citation_provenance_evidence(
        reproducibility,
        citation_live_provenance,
        mock_evidence=mock_evidence,
        mixed_evidence=mixed_evidence,
    )
    level = "mock" if mock_evidence else "mixed" if mixed_evidence or reproducibility.get("verdict") == "WARN" else "live"
    return {
        "level": level,
        "mock_evidence": mock_evidence,
        "mixed_evidence": mixed_evidence,
        "citation_support_review_live": citation_support_review_live,
        "citation_registry_verification_invoked": citation_registry_verification_invoked,
        "citation_registry_live_verified_count": citation_registry_live_verified_count,
        "semantic_scholar_required": semantic_scholar_required,
        "watermark_required": level != "live",
    }


__all__ = ["_append_citation_provenance_evidence", "_provenance_trust"]
