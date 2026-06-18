from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import Any

from paperorchestra.runtime.readiness_full_run import (
    claim_safe_profile,
    full_live_run_blockers,
    full_live_run_profile,
)
from paperorchestra.runtime.readiness_profile_types import TRUTHY_ENV_VALUES, _profile


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
        full_missing, full_steps = full_live_run_blockers(self)
        return [
            self._local_cli_profile(),
            self._shell_provider_profile(),
            self._omx_native_profile(),
            self._live_verification_profile(),
            self._compile_profile(),
            full_live_run_profile(self, full_missing, full_steps),
            claim_safe_profile(self, full_missing, full_steps),
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
            steps.append("paperorchestra environment --summary")
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
