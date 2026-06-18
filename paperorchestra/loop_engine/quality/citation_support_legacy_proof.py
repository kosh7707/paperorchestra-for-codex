from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paperorchestra.loop_engine.quality.utils import _file_sha256
from paperorchestra.runtime.provider_web_prefix import exec_argv_prefix_proves_web_search


def _provider_proof_is_trusted(provenance: dict[str, Any], expected_direct_digest: str | None) -> bool:
    if provenance.get("web_search_capable") is not True or not provenance.get("provider_command_digest"):
        return False
    proof = provenance.get("provider_capability_proof")
    if proof == "direct-codex-search/1" or proof is None:
        return bool(expected_direct_digest and provenance.get("provider_command_digest") == expected_direct_digest)
    if proof != "provider-wrapper-contract/1":
        return False
    contract_path = provenance.get("provider_contract_path")
    wrapper_path = provenance.get("provider_wrapper_path")
    if not isinstance(contract_path, str) or not isinstance(wrapper_path, str):
        return False
    contract = Path(contract_path)
    wrapper = Path(wrapper_path)
    if not contract.exists() or not wrapper.exists():
        return False
    if _file_sha256(contract) != provenance.get("provider_contract_sha256"):
        return False
    if _file_sha256(wrapper) != provenance.get("provider_wrapper_sha256"):
        return False
    payload = _read_provider_contract(contract)
    if payload is None:
        return False
    if not _contract_points_to_wrapper(payload, contract=contract, wrapper=wrapper):
        return False
    mode = payload.get("modes", {}).get("web") if isinstance(payload.get("modes"), dict) else None
    return _web_mode_contract_is_trusted(mode, provenance=provenance)


def _read_provider_contract(contract: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(contract.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("schema_version") != "provider-wrapper-contract/1":
        return None
    return payload


def _contract_points_to_wrapper(payload: dict[str, Any], *, contract: Path, wrapper: Path) -> bool:
    try:
        recorded = Path(str(payload.get("wrapper_path") or ""))
        if not recorded.is_absolute():
            recorded = contract.parent / recorded
        return recorded.resolve() == wrapper.resolve()
    except (OSError, RuntimeError):
        return False


def _web_mode_contract_is_trusted(mode: Any, *, provenance: dict[str, Any]) -> bool:
    if not isinstance(mode, dict):
        return False
    redacted_prefix_proof = (
        mode.get("search_enabled") is True
        and isinstance(mode.get("exec_argv_prefix_label"), str)
        and str(mode.get("exec_argv_prefix_label")).startswith("redacted-exec-argv-prefix:")
        and isinstance(mode.get("exec_argv_prefix_sha256"), str)
        and len(str(mode.get("exec_argv_prefix_sha256"))) == 64
    )
    return (
        mode.get("trace_wrapped") is True
        and mode.get("web_search_capable") is True
        and (exec_argv_prefix_proves_web_search(mode.get("exec_argv_prefix")) or redacted_prefix_proof)
        and provenance.get("provider_wrapper_mode") == "web"
    )


def _trace_matches_provider_proof(trace_payload: dict[str, Any], provenance: dict[str, Any]) -> bool:
    for key in [
        "provider_capability_proof",
        "provider_contract_path",
        "provider_contract_sha256",
        "provider_wrapper_path",
        "provider_wrapper_sha256",
        "provider_wrapper_mode",
    ]:
        if provenance.get(key) is not None and trace_payload.get(key) != provenance.get(key):
            return False
    return True
