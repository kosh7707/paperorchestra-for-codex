from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.quality.citation_support_legacy_contract import (
    _contract_points_to_wrapper,
    _read_provider_contract,
    _web_mode_contract_is_trusted,
    _wrapper_contract_proof_is_trusted,
)

_PROVIDER_PROOF_KEYS = [
    "provider_capability_proof",
    "provider_contract_path",
    "provider_contract_sha256",
    "provider_wrapper_path",
    "provider_wrapper_sha256",
    "provider_wrapper_mode",
]


def _trace_matches_provider_proof(trace_payload: dict[str, Any], provenance: dict[str, Any]) -> bool:
    for key in _PROVIDER_PROOF_KEYS:
        if provenance.get(key) is not None and trace_payload.get(key) != provenance.get(key):
            return False
    return True


def _provider_proof_is_trusted(provenance: dict[str, Any], expected_direct_digest: str | None) -> bool:
    if provenance.get("web_search_capable") is not True or not provenance.get("provider_command_digest"):
        return False
    proof = provenance.get("provider_capability_proof")
    if proof == "direct-codex-search/1" or proof is None:
        return bool(expected_direct_digest and provenance.get("provider_command_digest") == expected_direct_digest)
    if proof != "provider-wrapper-contract/1":
        return False
    return _wrapper_contract_proof_is_trusted(provenance)


__all__ = [
    "_contract_points_to_wrapper",
    "_provider_proof_is_trusted",
    "_read_provider_contract",
    "_trace_matches_provider_proof",
    "_web_mode_contract_is_trusted",
]
