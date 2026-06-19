from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class CompileEnvironmentReport:
    latex_engine: str | None
    sandbox_tool: str | None
    sandbox_wrapper_path: str | None
    auto_configured_wrapper: bool
    ready_for_compile: bool
    package_manager: str | None
    bootstrap_script_path: str | None
    install_context: dict[str, Any]
    install_commands: list[str]
    fallback_install_commands: list[str]
    omx_optional_install_commands: list[str]
    requires_privilege_escalation: bool
    cargo_path: str | None
    pkg_config_path: str | None
    user_space_probe: dict[str, Any] | None
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


__all__ = ["CompileEnvironmentReport"]
