from __future__ import annotations

from typing import Any


def _base_provenance_evidence(reproducibility: dict[str, Any]) -> tuple[list[str], list[str]]:
    mock_evidence: list[str] = []
    mixed_evidence: list[str] = []
    if reproducibility.get("latest_provider_name") == "mock":
        mock_evidence.append("provider_name=mock")
    if reproducibility.get("latest_verify_mode") == "mock":
        mock_evidence.append("verify_mode=mock")
    if reproducibility.get("latest_verify_fallback_used") == "mock":
        mock_evidence.append("verify_fallback_used=mock")
    if int(reproducibility.get("prompt_trace_file_count") or 0) == 0:
        mixed_evidence.append("prompt_trace_missing")
    if (reproducibility.get("lane_manifest_summary") or {}).get("manifest_count", 0) == 0:
        mixed_evidence.append("lane_manifest_missing")
    if not bool(reproducibility.get("verification_invoked")):
        mixed_evidence.append("citation_registry_live_verification_not_invoked")
    return mock_evidence, mixed_evidence


def _append_citation_provenance_evidence(
    reproducibility: dict[str, Any],
    citation_live_provenance: Any,
    *,
    mock_evidence: list[str],
    mixed_evidence: list[str],
) -> None:
    if not isinstance(citation_live_provenance, dict):
        if int(reproducibility.get("mock_registry_entry_count") or 0) > 0:
            mock_evidence.append(f"mock_registry_entry_count={reproducibility.get('mock_registry_entry_count')}")
        return

    has_cited_counts = any(
        key in citation_live_provenance for key in ("cited_curated_seed_count", "cited_mixed_count", "cited_mock_count")
    )
    cited_curated_seed_count = int(citation_live_provenance.get("cited_curated_seed_count") or 0)
    cited_mixed_count = int(citation_live_provenance.get("cited_mixed_count") or 0)
    cited_mock_count = int(citation_live_provenance.get("cited_mock_count") or 0)
    if cited_mock_count > 0:
        mock_evidence.append(f"citation_cited_mock_count={cited_mock_count}")
    if cited_curated_seed_count > 0:
        mixed_evidence.append(f"citation_cited_curated_seed_count={cited_curated_seed_count}")
    if cited_mixed_count > 0:
        mixed_evidence.append(f"citation_cited_mixed_count={cited_mixed_count}")
    if not has_cited_counts:
        if int(reproducibility.get("mock_registry_entry_count") or 0) > 0:
            mock_evidence.append(f"mock_registry_entry_count={reproducibility.get('mock_registry_entry_count')}")
        seed_only_count = int(citation_live_provenance.get("seed_only_count") or 0)
        if seed_only_count > 0:
            mixed_evidence.append(f"citation_registry_seed_only_count={seed_only_count}")
    status = str(citation_live_provenance.get("status") or "")
    if status in {"missing", "unreadable", "malformed", "empty"}:
        mixed_evidence.append(f"citation_live_provenance_status={status}")
