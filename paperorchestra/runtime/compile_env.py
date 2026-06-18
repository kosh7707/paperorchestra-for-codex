from __future__ import annotations

import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from paperorchestra.runtime.compile_install import (
    _bootstrap_script_contents,
    _install_command_context,
    _install_command_templates,
    _sudo_usable,
    _with_prefix,
)

from paperorchestra.runtime.compile_sandbox import (
    SANDBOX_TOOLS,
    _command_text,
    _detect_sandbox_tool_with_notes,
    _sandbox_probe_command,
    _sandbox_tool_usable,
    _trim_probe_output,
    _wrapper_script_contents,
    _write_sandbox_wrapper,
    detect_sandbox_tool,
)


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


LATEX_ENGINES = ["latexmk", "pdflatex", "tectonic"]
PACKAGE_MANAGERS = ["apt-get", "dnf", "yum", "pacman", "brew", "apk"]


def detect_latex_engine() -> str | None:
    for engine in LATEX_ENGINES:
        path = shutil.which(engine)
        if path:
            return path
    return None


def detect_package_manager() -> str | None:
    for tool in PACKAGE_MANAGERS:
        path = shutil.which(tool)
        if path:
            return path
    return None


def detect_cargo() -> str | None:
    return shutil.which("cargo")


def detect_pkg_config() -> str | None:
    return shutil.which("pkg-config") or shutil.which("pkgconf")


def ensure_bootstrap_script(cwd: str | Path | None) -> str | None:
    package_manager = detect_package_manager()
    if not package_manager:
        return None
    tools_dir = Path(cwd or ".").resolve() / ".paper-orchestra" / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    script = tools_dir / "bootstrap-compile-env.sh"
    script.write_text(_bootstrap_script_contents(package_manager), encoding="utf-8")
    script.chmod(0o755)
    return str(script)


def ensure_sandbox_wrapper(cwd: str | Path | None, *, tool_path: str | None = None) -> str | None:
    tool = tool_path or detect_sandbox_tool()
    if not tool:
        return None
    return _write_sandbox_wrapper(cwd, tool)


def inspect_compile_environment(cwd: str | Path | None, *, auto_configure_wrapper: bool = True) -> CompileEnvironmentReport:
    notes: list[str] = []
    latex_engine = detect_latex_engine()
    sandbox_tool, sandbox_probe_notes = _detect_sandbox_tool_with_notes()
    package_manager = detect_package_manager()
    cargo_path = detect_cargo()
    pkg_config_path = detect_pkg_config()
    wrapper_path = os.environ.get("PAPERO_TEX_SANDBOX_CMD")
    bootstrap_script_path = ensure_bootstrap_script(cwd)
    auto_configured = False
    install_context = _install_command_context()
    install_commands = _install_command_templates(package_manager, install_context) if package_manager else []
    requires_privilege_escalation = bool(
        install_commands and not install_context.get("is_root") and not install_context.get("can_run_install_commands_directly")
    )
    fallback_install_commands: list[str] = []
    omx_optional_install_commands: list[str] = []
    if package_manager and Path(package_manager).name in {"apt-get", "apt"} and (install_context.get("is_root") or install_context.get("sudo_available")):
        prefix = install_context.get("command_prefix") or ""
        fallback_install_commands.append(_with_prefix("apt-get install -y firejail", prefix))
        omx_optional_install_commands.append(_with_prefix("apt-get install -y xz-utils", prefix))
    user_space_probe: dict[str, Any] | None = None

    if not latex_engine:
        notes.append("No supported LaTeX engine found (latexmk/pdflatex/tectonic).")
    else:
        notes.append(f"Detected LaTeX engine: {latex_engine}")

    notes.extend(sandbox_probe_notes)
    if not sandbox_tool:
        notes.append("No supported sandbox tool passed runtime usability probe (bwrap/firejail/nsjail).")
    else:
        notes.append(f"Selected sandbox tool: {sandbox_tool}")
    if not sandbox_tool and package_manager and Path(package_manager).name in {"apt-get", "apt"}:
        notes.append(
            "If bwrap is installed but unusable in this container, install a fallback sandbox such as firejail "
            f"({fallback_install_commands[0] if fallback_install_commands else 'apt-get install -y firejail'}) or set PAPERO_TEX_SANDBOX_CMD."
        )

    if package_manager:
        notes.append(f"Detected package manager: {package_manager}")
    else:
        notes.append("No supported package manager detected for automatic remediation.")

    if cargo_path:
        notes.append(f"Detected cargo: {cargo_path}")
        user_space_probe = {
            "cargo_available": True,
            "pkg_config_available": bool(pkg_config_path),
            "tectonic_install_hint": (
                "cargo install tectonic --locked"
                if pkg_config_path
                else "cargo is available, but user-space tectonic install is currently blocked because pkg-config is missing."
            ),
        }
    else:
        user_space_probe = {
            "cargo_available": False,
            "pkg_config_available": bool(pkg_config_path),
            "tectonic_install_hint": "cargo is not available for a user-space tectonic install.",
        }

    if pkg_config_path:
        notes.append(f"Detected pkg-config: {pkg_config_path}")
    else:
        notes.append("pkg-config is not available; cargo-based tectonic installation will fail until it is installed.")

    if not wrapper_path and auto_configure_wrapper and sandbox_tool:
        wrapper = ensure_sandbox_wrapper(cwd, tool_path=sandbox_tool)
        if wrapper:
            wrapper_path = f'["{wrapper}"]'
            auto_configured = True
            notes.append(f"Auto-configured sandbox wrapper: {wrapper}")

    if not wrapper_path:
        notes.append("Sandbox wrapper command is not configured.")
    if bootstrap_script_path:
        notes.append(f"Bootstrap script available: {bootstrap_script_path}")
    if package_manager and not install_commands and not install_context.get("is_root") and not install_context.get("sudo_available"):
        notes.append("Install commands require root privileges, but this user is not root and sudo is not available.")
    elif requires_privilege_escalation:
        notes.append("Install commands likely require elevated privileges and passwordless sudo is not available.")
    if omx_optional_install_commands:
        notes.append(f"For OMX explore/control surfaces in minimal containers, xz-utils may be required: {omx_optional_install_commands[0]}")

    ready = bool(latex_engine and wrapper_path)
    return CompileEnvironmentReport(
        latex_engine=latex_engine,
        sandbox_tool=sandbox_tool,
        sandbox_wrapper_path=wrapper_path,
        auto_configured_wrapper=auto_configured,
        ready_for_compile=ready,
        package_manager=package_manager,
        bootstrap_script_path=bootstrap_script_path,
        install_context=install_context,
        install_commands=install_commands,
        fallback_install_commands=fallback_install_commands,
        omx_optional_install_commands=omx_optional_install_commands,
        requires_privilege_escalation=requires_privilege_escalation,
        cargo_path=cargo_path,
        pkg_config_path=pkg_config_path,
        user_space_probe=user_space_probe,
        notes=notes,
    )
