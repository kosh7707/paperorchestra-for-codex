from __future__ import annotations

from typing import Protocol

from paperorchestra.runtime.readiness_profile_types import _profile


class FullRunReadiness(Protocol):
    provider_command_configured: bool
    omx_ready: bool
    semantic_scholar_api_key_set: bool
    compile_ready: bool
    strict_omx_native: bool
    strict_content_gates: bool
    omx_available: bool
    codex_available: bool


def full_live_run_blockers(builder: FullRunReadiness) -> tuple[list[str], list[str]]:
    missing: list[str] = []
    steps: list[str] = []
    if not builder.provider_command_configured:
        missing.append("Shell-provider command not configured.")
    if not builder.omx_ready:
        if not builder.omx_available or not builder.codex_available:
            missing.append("OMX/Codex toolchain not fully installed.")
        else:
            missing.append("OMX control surface probe did not pass.")
    if not builder.semantic_scholar_api_key_set:
        missing.append("Semantic Scholar API key missing.")
    if not builder.compile_ready:
        missing.append("Compile environment is not fully ready.")
    if missing:
        steps.extend([
            "paperorchestra environment",
            "paperorchestra doctor",
            "paperorchestra quality-gate --no-fail-on-block",
        ])
    return missing, steps


def full_live_run_profile(builder: FullRunReadiness, missing: list[str], steps: list[str]) -> dict[str, object]:
    return _profile(
        "full_live_run_ready",
        "Live shell-provider + OMX-native + live verification + compile runs.",
        builder.provider_command_configured
        and builder.omx_ready
        and builder.semantic_scholar_api_key_set
        and builder.compile_ready,
        list(missing),
        list(steps) or ["paperorchestra run --provider shell --runtime-mode omx_native --verify-mode live --compile"],
    )


def claim_safe_profile(builder: FullRunReadiness, full_missing: list[str], full_steps: list[str]) -> dict[str, object]:
    missing = list(full_missing)
    steps = list(full_steps)
    if not builder.strict_omx_native:
        missing.append("Enable strict OMX-native mode for claim-safe runs.")
        steps.append("export PAPERO_STRICT_OMX_NATIVE=1")
    if not builder.strict_content_gates:
        missing.append("Enable strict content gates for claim-safe runs.")
        steps.append("export PAPERO_STRICT_CONTENT_GATES=1")
    return _profile(
        "claim_safe_full_run_ready",
        "The stricter posture for reproducibility/fidelity claims: full live run plus strict OMX-native no-fallback policy.",
        builder.provider_command_configured
        and builder.omx_ready
        and builder.semantic_scholar_api_key_set
        and builder.compile_ready
        and builder.strict_omx_native
        and builder.strict_content_gates,
        missing,
        steps or ["paperorchestra quality-gate --no-fail-on-block"],
    )
