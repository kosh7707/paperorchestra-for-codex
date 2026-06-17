from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from paperorchestra.runtime.provider_base import BaseProvider
from paperorchestra.runtime.shell_provider import ShellProvider


def default_codex_web_provider_command() -> str:
    command = ["codex", "--search", "exec", "--skip-git-repo-check"]
    if model := os.environ.get("PAPERO_OMX_MODEL"):
        command.extend(["-m", model])
    if effort := os.environ.get("PAPERO_OMX_REASONING_EFFORT"):
        command.extend(["-c", f'model_reasoning_effort="{effort}"'])
    return json.dumps(command)


def provider_command_digest(provider: BaseProvider | None) -> str | None:
    if isinstance(provider, ShellProvider):
        return hashlib_sha256_json(provider.argv)
    return None


def hashlib_sha256_json(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False).encode("utf-8")).hexdigest()


def _read_wrapper_contract(wrapper_path: Path) -> dict[str, object] | None:
    contract_path = wrapper_path.with_name("provider-wrap.contract.json")
    if not contract_path.exists():
        return None
    try:
        payload = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def exec_argv_prefix_proves_web_search(prefix: object) -> bool:
    return (
        isinstance(prefix, list)
        and len(prefix) >= 3
        and [str(item) for item in prefix[-2:]] == ["--search", "exec"]
        and all(isinstance(item, str) and item.strip() for item in prefix)
    )


def _contract_wrapper_path(contract_path: Path, payload: dict[str, object]) -> Path | None:
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


def _redacted_exec_argv_prefix_proves_web_search(mode_payload: dict[str, object]) -> bool:
    return (
        mode_payload.get("search_enabled") is True
        and isinstance(mode_payload.get("exec_argv_prefix_label"), str)
        and str(mode_payload.get("exec_argv_prefix_label")).startswith("redacted-exec-argv-prefix:")
        and isinstance(mode_payload.get("exec_argv_prefix_sha256"), str)
        and len(str(mode_payload.get("exec_argv_prefix_sha256"))) == 64
    )


def provider_web_search_capability_proof(provider: BaseProvider) -> dict[str, object] | None:
    """Return auditable web-search capability proof for trusted citation providers.

    Fresh smoke uses a trace wrapper (`bash provider-wrap.sh web`) so prompt/response
    evidence is preserved.  Direct `codex --search exec` remains valid for ordinary
    web-capable shell providers, but wrapper-backed web support is accepted only when
    an adjacent sidecar proves the wrapper path, hash, mode, and inner argv prefix.
    """

    if not isinstance(provider, ShellProvider):
        return None
    argv = provider.argv
    digest = hashlib_sha256_json(argv)
    if len(argv) >= 3 and Path(argv[0]).name == "codex" and argv[1] == "--search" and argv[2] == "exec":
        return {
            "provider_capability_proof": "direct-codex-search/1",
            "provider_command_digest": digest,
            "web_search_capable": True,
        }
    if len(argv) != 3 or Path(argv[0]).name not in {"bash", "sh"} or argv[2] != "web":
        return None
    wrapper_path = Path(argv[1]).resolve()
    if wrapper_path.name != "provider-wrap.sh" or not wrapper_path.exists():
        return None
    contract_path = wrapper_path.with_name("provider-wrap.contract.json")
    payload = _read_wrapper_contract(wrapper_path)
    if not payload or payload.get("schema_version") != "provider-wrapper-contract/1":
        return None
    recorded_path = _contract_wrapper_path(contract_path, payload)
    if recorded_path != wrapper_path:
        return None
    actual_wrapper_sha = hashlib.sha256(wrapper_path.read_bytes()).hexdigest()
    if payload.get("wrapper_sha256") != actual_wrapper_sha:
        return None
    modes = payload.get("modes")
    mode_payload = modes.get("web") if isinstance(modes, dict) else None
    if not isinstance(mode_payload, dict):
        return None
    if mode_payload.get("trace_wrapped") is not True or mode_payload.get("web_search_capable") is not True:
        return None
    prefix = mode_payload.get("exec_argv_prefix")
    raw_prefix_proves_web = exec_argv_prefix_proves_web_search(prefix)
    redacted_prefix_proves_web = _redacted_exec_argv_prefix_proves_web_search(mode_payload)
    if not (raw_prefix_proves_web or redacted_prefix_proves_web):
        return None
    contract_sha = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    proof: dict[str, object] = {
        "provider_capability_proof": "provider-wrapper-contract/1",
        "provider_command_digest": digest,
        "provider_contract_path": str(contract_path),
        "provider_contract_sha256": contract_sha,
        "provider_wrapper_path": str(wrapper_path),
        "provider_wrapper_sha256": actual_wrapper_sha,
        "provider_wrapper_mode": "web",
        "web_search_capable": True,
    }
    if raw_prefix_proves_web:
        proof["provider_wrapper_exec_argv_prefix"] = prefix
    else:
        proof["provider_wrapper_exec_argv_prefix_label"] = mode_payload.get("exec_argv_prefix_label")
        proof["provider_wrapper_exec_argv_prefix_sha256"] = mode_payload.get("exec_argv_prefix_sha256")
    return proof


def provider_supports_web_search(provider: BaseProvider) -> bool:
    return provider_web_search_capability_proof(provider) is not None
