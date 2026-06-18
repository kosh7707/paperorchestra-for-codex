from __future__ import annotations

from typing import Any

from paperorchestra.runtime.readiness_profile_builder import (
    TRUTHY_ENV_VALUES,
    ReadinessProfileBuilder,
    _profile,
)


def build_readiness_profiles(
    *,
    omx_available: bool,
    codex_available: bool,
    omx_control_surface_ready: bool = True,
    omx_control_surface_missing: list[str] | None = None,
    omx_control_surface_next_steps: list[str] | None = None,
    provider_command_configured: bool,
    semantic_scholar_api_key_set: bool,
    compile_environment_ready: bool,
    tex_compile_opt_in: bool,
    strict_omx_native: bool,
) -> list[dict[str, Any]]:
    return ReadinessProfileBuilder(
        omx_available=omx_available,
        codex_available=codex_available,
        omx_control_surface_ready=omx_control_surface_ready,
        omx_control_surface_missing=omx_control_surface_missing or [],
        omx_control_surface_next_steps=omx_control_surface_next_steps or [],
        provider_command_configured=provider_command_configured,
        semantic_scholar_api_key_set=semantic_scholar_api_key_set,
        compile_environment_ready=compile_environment_ready,
        tex_compile_opt_in=tex_compile_opt_in,
        strict_omx_native=strict_omx_native,
    ).build()


__all__ = [
    "TRUTHY_ENV_VALUES",
    "ReadinessProfileBuilder",
    "_profile",
    "build_readiness_profiles",
]
