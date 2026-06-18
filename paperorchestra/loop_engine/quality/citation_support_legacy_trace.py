from __future__ import annotations

from typing import Any

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
