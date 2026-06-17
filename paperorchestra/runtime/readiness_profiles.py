from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import Any


TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}


def _profile(name: str, description: str, ready: bool, missing: list[str], next_steps: list[str]) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "ready": ready,
        "status": "ok" if ready else "warning",
        "missing": missing,
        "next_steps": next_steps,
    }


@dataclass
class ReadinessProfileBuilder:
    omx_available: bool
    codex_available: bool
    provider_command_configured: bool
    semantic_scholar_api_key_set: bool
    compile_environment_ready: bool
    tex_compile_opt_in: bool
    strict_omx_native: bool
    omx_control_surface_ready: bool = True
    omx_control_surface_missing: list[str] = field(default_factory=list)
    omx_control_surface_next_steps: list[str] = field(default_factory=list)

    @property
    def strict_content_gates(self) -> bool:
        return os.environ.get("PAPERO_STRICT_CONTENT_GATES", "").strip().lower() in TRUTHY_ENV_VALUES

    @property
    def omx_ready(self) -> bool:
        return self.omx_available and self.codex_available and self.omx_control_surface_ready

    @property
    def compile_ready(self) -> bool:
        return self.compile_environment_ready and self.tex_compile_opt_in

    def build(self) -> list[dict[str, Any]]:
        full_missing, full_steps = self._full_live_run_blockers()
        return [
            self._local_cli_profile(),
            self._shell_provider_profile(),
            self._omx_native_profile(),
            self._live_verification_profile(),
            self._compile_profile(),
            self._full_live_run_profile(full_missing, full_steps),
            self._claim_safe_profile(full_missing, full_steps),
        ]

    def _local_cli_profile(self) -> dict[str, Any]:
        return _profile(
            "local_cli_ready",
            "Local CLI/help/status surfaces are available.",
            True,
            [],
            ["paperorchestra status --json", "paperorchestra doctor"],
        )

    def _shell_provider_profile(self) -> dict[str, Any]:
        missing: list[str] = []
        steps: list[str] = []
        if not self.provider_command_configured:
            missing.append("Set PAPERO_MODEL_CMD for shell-provider runs.")
            steps.append("Run ./scripts/install.sh for the generic Codex provider command or set PAPERO_MODEL_CMD to your Codex/OpenAI/Ollama command.")
        return _profile(
            "shell_provider_ready",
            "CLI runs that use `--provider shell` instead of the mock provider.",
            self.provider_command_configured,
            missing,
            steps or ["paperorchestra run --provider shell --verify-mode mock --runtime-mode compatibility"],
        )

    def _omx_native_profile(self) -> dict[str, Any]:
        missing: list[str] = []
        steps: list[str] = []
        if not self.omx_available:
            missing.append("Install `omx` and ensure it is on PATH.")
            steps.append("omx doctor")
        if not self.codex_available:
            missing.append("Install `codex` and ensure it is on PATH.")
            steps.append("codex --help")
        if self.omx_available and self.codex_available and not self.omx_control_surface_ready:
            missing.extend(self.omx_control_surface_missing or ["OMX control surface probe did not pass."])
            steps.extend(self.omx_control_surface_next_steps)
        return _profile(
            "omx_native_ready",
            "Live OMX-native stage execution (`--runtime-mode omx_native`).",
            self.omx_ready,
            missing,
            steps or ["paperorchestra run --provider shell --runtime-mode omx_native --verify-mode mock"],
        )

    def _live_verification_profile(self) -> dict[str, Any]:
        missing: list[str] = []
        steps: list[str] = []
        if not self.semantic_scholar_api_key_set:
            missing.append("Set SEMANTIC_SCHOLAR_API_KEY for authenticated Semantic Scholar traffic.")
            steps.append("export SEMANTIC_SCHOLAR_API_KEY='<your-key>'")
        return _profile(
            "live_verification_ready",
            "Live literature verification and search-grounded discovery with less rate-limit risk.",
            self.semantic_scholar_api_key_set,
            missing,
            steps or ["paperorchestra run --provider shell --discovery-mode search-grounded"],
        )

    def _compile_profile(self) -> dict[str, Any]:
        missing: list[str] = []
        steps: list[str] = []
        if not self.compile_environment_ready:
            missing.append("Install a supported LaTeX engine and sandbox tool, or run the compile bootstrap guidance.")
            steps.extend(["paperorchestra environment --summary", "paperorchestra environment --summary"])
        if not self.tex_compile_opt_in:
            missing.append("Set PAPERO_ALLOW_TEX_COMPILE=1 before running compile commands.")
            steps.append("export PAPERO_ALLOW_TEX_COMPILE=1")
        return _profile(
            "compile_ready",
            "Paper compilation with the guarded TeX toolchain.",
            self.compile_ready,
            missing,
            steps or ["paperorchestra compile"],
        )

    def _full_live_run_blockers(self) -> tuple[list[str], list[str]]:
        missing: list[str] = []
        steps: list[str] = []
        if not self.provider_command_configured:
            missing.append("Shell-provider command not configured.")
        if not self.omx_ready:
            if not self.omx_available or not self.codex_available:
                missing.append("OMX/Codex toolchain not fully installed.")
            else:
                missing.append("OMX control surface probe did not pass.")
        if not self.semantic_scholar_api_key_set:
            missing.append("Semantic Scholar API key missing.")
        if not self.compile_ready:
            missing.append("Compile environment is not fully ready.")
        if missing:
            steps.extend([
                "paperorchestra environment",
                "paperorchestra doctor",
                "paperorchestra quality-gate --no-fail-on-block",
            ])
        return missing, steps

    def _full_live_run_profile(self, missing: list[str], steps: list[str]) -> dict[str, Any]:
        return _profile(
            "full_live_run_ready",
            "Live shell-provider + OMX-native + live verification + compile runs.",
            self.provider_command_configured
            and self.omx_ready
            and self.semantic_scholar_api_key_set
            and self.compile_ready,
            list(missing),
            list(steps) or ["paperorchestra run --provider shell --runtime-mode omx_native --verify-mode live --compile"],
        )

    def _claim_safe_profile(self, full_missing: list[str], full_steps: list[str]) -> dict[str, Any]:
        missing = list(full_missing)
        steps = list(full_steps)
        if not self.strict_omx_native:
            missing.append("Enable strict OMX-native mode for claim-safe runs.")
            steps.append("export PAPERO_STRICT_OMX_NATIVE=1")
        if not self.strict_content_gates:
            missing.append("Enable strict content gates for claim-safe runs.")
            steps.append("export PAPERO_STRICT_CONTENT_GATES=1")
        return _profile(
            "claim_safe_full_run_ready",
            "The stricter posture for reproducibility/fidelity claims: full live run plus strict OMX-native no-fallback policy.",
            self.provider_command_configured
            and self.omx_ready
            and self.semantic_scholar_api_key_set
            and self.compile_ready
            and self.strict_omx_native
            and self.strict_content_gates,
            missing,
            steps or ["paperorchestra quality-gate --no-fail-on-block"],
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
