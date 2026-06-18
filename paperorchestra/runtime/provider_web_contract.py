from __future__ import annotations

import hashlib
import json
from pathlib import Path

from paperorchestra.runtime.provider_web_prefix import (
    exec_argv_prefix_proves_web_search,
    redacted_exec_argv_prefix_proves_web_search,
)


def wrapper_contract_capability_proof(argv: list[str], *, provider_command_digest: str) -> dict[str, object] | None:
    if len(argv) != 3 or Path(argv[0]).name not in {"bash", "sh"} or argv[2] != "web":
        return None
    wrapper_path = Path(argv[1]).resolve()
    if wrapper_path.name != "provider-wrap.sh" or not wrapper_path.exists():
        return None
    contract_path = wrapper_path.with_name("provider-wrap.contract.json")
    payload = read_wrapper_contract(wrapper_path)
    if not payload or payload.get("schema_version") != "provider-wrapper-contract/1":
        return None
    recorded_path = contract_wrapper_path(contract_path, payload)
    if recorded_path != wrapper_path:
        return None
    actual_wrapper_sha = hashlib.sha256(wrapper_path.read_bytes()).hexdigest()
    if payload.get("wrapper_sha256") != actual_wrapper_sha:
        return None
    mode_payload = _web_mode_payload(payload)
    if mode_payload is None:
        return None
    raw_prefix_proves_web = exec_argv_prefix_proves_web_search(mode_payload.get("exec_argv_prefix"))
    redacted_prefix_proves_web = redacted_exec_argv_prefix_proves_web_search(mode_payload)
    if not (raw_prefix_proves_web or redacted_prefix_proves_web):
        return None
    proof = _base_wrapper_proof(
        provider_command_digest=provider_command_digest,
        contract_path=contract_path,
        wrapper_path=wrapper_path,
        wrapper_sha=actual_wrapper_sha,
    )
    if raw_prefix_proves_web:
        proof["provider_wrapper_exec_argv_prefix"] = mode_payload.get("exec_argv_prefix")
    else:
        proof["provider_wrapper_exec_argv_prefix_label"] = mode_payload.get("exec_argv_prefix_label")
        proof["provider_wrapper_exec_argv_prefix_sha256"] = mode_payload.get("exec_argv_prefix_sha256")
    return proof


def read_wrapper_contract(wrapper_path: Path) -> dict[str, object] | None:
    contract_path = wrapper_path.with_name("provider-wrap.contract.json")
    if not contract_path.exists():
        return None
    try:
        payload = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def contract_wrapper_path(contract_path: Path, payload: dict[str, object]) -> Path | None:
    value = payload.get("wrapper_path")
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        recorded_path = Path(value)
        if not recorded_path.is_absolute():
            recorded_path = contract_path.parent / recorded_path
        return recorded_path.resolve()
    except (OSError, RuntimeError):
        return None


def _web_mode_payload(payload: dict[str, object]) -> dict[str, object] | None:
    modes = payload.get("modes")
    mode_payload = modes.get("web") if isinstance(modes, dict) else None
    if not isinstance(mode_payload, dict):
        return None
    if mode_payload.get("trace_wrapped") is not True or mode_payload.get("web_search_capable") is not True:
        return None
    return mode_payload


def _base_wrapper_proof(
    *,
    provider_command_digest: str,
    contract_path: Path,
    wrapper_path: Path,
    wrapper_sha: str,
) -> dict[str, object]:
    return {
        "provider_capability_proof": "provider-wrapper-contract/1",
        "provider_command_digest": provider_command_digest,
        "provider_contract_path": str(contract_path),
        "provider_contract_sha256": hashlib.sha256(contract_path.read_bytes()).hexdigest(),
        "provider_wrapper_path": str(wrapper_path),
        "provider_wrapper_sha256": wrapper_sha,
        "provider_wrapper_mode": "web",
        "web_search_capable": True,
    }
