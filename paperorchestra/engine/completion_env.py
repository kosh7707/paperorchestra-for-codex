from __future__ import annotations

import math
import os

from paperorchestra.runtime.provider_base import CompletionRequest


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _strict_omx_native_enabled() -> bool:
    return _env_flag("PAPERO_STRICT_OMX_NATIVE")


def _env_float(name: str) -> float | None:
    raw = os.environ.get(name)
    if raw in {None, ""}:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _env_int(name: str) -> int | None:
    raw = os.environ.get(name)
    if raw in {None, ""}:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _build_completion_request(*, system_prompt: str, user_prompt: str) -> CompletionRequest:
    return CompletionRequest(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=_env_float("PAPERO_PROVIDER_TEMPERATURE"),
        max_output_tokens=_env_int("PAPERO_PROVIDER_MAX_OUTPUT_TOKENS"),
        seed=_env_int("PAPERO_PROVIDER_SEED"),
    )
