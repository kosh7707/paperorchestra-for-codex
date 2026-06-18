from __future__ import annotations

import hashlib
import json
from typing import Any

from paperorchestra.core.models import utc_now_iso
from paperorchestra.runtime.provider_base import BaseProvider, CompletionRequest
from paperorchestra.runtime.shell_provider import ShellProvider

from .completion_env import _strict_omx_native_enabled


def _provider_name(provider: BaseProvider | None) -> str | None:
    if provider is None:
        return None
    return getattr(provider, "name", provider.__class__.__name__.lower())


def _lane_owner(lane_type: str, fallback_used: bool) -> str:
    return "python-kernel" if fallback_used else lane_type


def _provider_identity_payload(
    provider: BaseProvider | None,
    *,
    runtime_mode: str,
    stage: str | None = None,
    request: CompletionRequest | None = None,
) -> dict[str, Any]:
    provider_name = _provider_name(provider)
    strict = _strict_omx_native_enabled()
    payload: dict[str, Any] = {
        "provider_name": provider_name,
        "runtime_mode": runtime_mode,
        "stage": stage,
        "strict_omx_native": strict,
        "provider_command_present": False,
        "provider_command_digest": None,
        "model_command_source": None,
        "resolved_backend_class": "unknown",
        "request_controls": request.control_summary() if request is not None else None,
        "generation_determinism": {
            "byte_identical_generation_claimed": False,
            "sampling_controls_are_passthrough_only": True,
            "rationale": (
                "PaperOrchestra records provider controls for auditability, but stochastic or "
                "agentic model backends may still produce non-identical text."
            ),
        },
        "generated_at": utc_now_iso(),
    }
    if provider_name == "mock":
        payload["resolved_backend_class"] = "mock"
        return payload
    if isinstance(provider, ShellProvider):
        command_repr = json.dumps(provider.argv, ensure_ascii=False)
        payload["provider_command_present"] = bool(provider.argv)
        payload["provider_command_digest"] = hashlib.sha256(command_repr.encode("utf-8")).hexdigest()
        payload["model_command_source"] = getattr(provider, "command_source", "unknown")
        payload["resolved_backend_class"] = "real_shell_backend" if provider.argv else "unknown"
        return payload
    return payload
