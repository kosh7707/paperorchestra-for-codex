from __future__ import annotations

import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
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
    install_commands: list[str]
    requires_privilege_escalation: bool
    cargo_path: str | None
    pkg_config_path: str | None
    user_space_probe: dict[str, Any] | None
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


LATEX_ENGINES = ["latexmk", "pdflatex", "tectonic"]
SANDBOX_TOOLS = ["bwrap", "firejail", "nsjail"]
PACKAGE_MANAGERS = ["apt-get", "dnf", "yum", "pacman", "brew", "apk"]


def detect_latex_engine() -> str | None:
    for engine in LATEX_ENGINES:
        path = shutil.which(engine)
        if path:
            return path
    return None


def detect_sandbox_tool() -> str | None:
    for tool in SANDBOX_TOOLS:
        path = shutil.which(tool)
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


def _sudo_usable() -> bool:
    sudo = shutil.which("sudo")
    if not sudo:
        return False
    try:
        import subprocess

        proc = subprocess.run([sudo, "-n", "true"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        return proc.returncode == 0
    except Exception:
        return False


def _install_command_templates(package_manager_path: str) -> list[str]:
    tool = Path(package_manager_path).name
    if tool == "apt-get":
        return [
            "sudo apt-get update",
            "sudo apt-get install -y pkg-config libpng-dev texlive-latex-base texlive-latex-recommended texlive-fonts-recommended latexmk bubblewrap",
        ]
    if tool == "dnf":
        return [
            "sudo dnf install -y texlive-latex texlive-collection-latexrecommended latexmk bubblewrap",
        ]
    if tool == "yum":
        return [
            "sudo yum install -y texlive texlive-latex latexmk bubblewrap",
        ]
    if tool == "pacman":
        return [
            "sudo pacman -Sy --noconfirm texlive-latexextra texlive-fontsextra texlive-bin latexmk bubblewrap",
        ]
    if tool == "brew":
        return [
            "brew install --cask mactex-no-gui || brew install basictex",
            "brew install latexmk",
        ]
    if tool == "apk":
        return [
            "sudo apk add texmf-dist texlive texlive-latexextra bubblewrap",
        ]
    return []


def _bootstrap_script_contents(package_manager_path: str) -> str:
    commands = _install_command_templates(package_manager_path)
    body = "\n".join(commands) if commands else 'echo "No known install recipe for this package manager." >&2\nexit 1'
    return f"""#!/usr/bin/env bash
set -euo pipefail

{body}
"""


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


def _wrapper_script_contents(tool_path: str) -> str:
    tool_name = Path(tool_path).name
    if tool_name == "bwrap":
        return f'''#!/usr/bin/env bash
set -euo pipefail
if [ "$#" -lt 1 ]; then
  echo "usage: $0 <command> [args...]" >&2
  exit 2
fi
args=(
  --unshare-all
  --share-net
  --die-with-parent
  --ro-bind /usr /usr
  --ro-bind /bin /bin
  --ro-bind /lib /lib
  --ro-bind /lib64 /lib64
  --ro-bind /etc /etc
  --proc /proc
  --dev /dev
  --tmpfs /tmp
  --bind "$PWD" "$PWD"
  --chdir "$PWD"
)
if [ -n "${{HOME:-}}" ] && [ -d "$HOME" ]; then
  args+=(--bind "$HOME" "$HOME" --setenv HOME "$HOME")
fi
if [ -d /var/lib/texmf ]; then
  args+=(--ro-bind /var/lib/texmf /var/lib/texmf)
fi
exec {tool_path} "${{args[@]}}" "$@"
'''
    if tool_name == "firejail":
        return f'''#!/usr/bin/env bash
set -euo pipefail
if [ "$#" -lt 1 ]; then
  echo "usage: $0 <command> [args...]" >&2
  exit 2
fi
exec {tool_path} --quiet --private="$PWD" --net=none "$@"
'''
    if tool_name == "nsjail":
        return f'''#!/usr/bin/env bash
set -euo pipefail
if [ "$#" -lt 1 ]; then
  echo "usage: $0 <command> [args...]" >&2
  exit 2
fi
exec {tool_path} -Mo --chroot "$PWD" --cwd / --disable_clone_newnet -- "$@"
'''
    raise ValueError(f"Unsupported sandbox tool: {tool_name}")


def ensure_sandbox_wrapper(cwd: str | Path | None) -> str | None:
    tool = detect_sandbox_tool()
    if not tool:
        return None
    tools_dir = Path(cwd or ".").resolve() / ".paper-orchestra" / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    wrapper = tools_dir / "tex-sandbox.sh"
    wrapper.write_text(_wrapper_script_contents(tool), encoding="utf-8")
    wrapper.chmod(0o755)
    return str(wrapper)


def inspect_compile_environment(cwd: str | Path | None, *, auto_configure_wrapper: bool = True) -> CompileEnvironmentReport:
    notes: list[str] = []
    latex_engine = detect_latex_engine()
    sandbox_tool = detect_sandbox_tool()
    package_manager = detect_package_manager()
    cargo_path = detect_cargo()
    pkg_config_path = detect_pkg_config()
    wrapper_path = os.environ.get("PAPERO_TEX_SANDBOX_CMD")
    bootstrap_script_path = ensure_bootstrap_script(cwd)
    auto_configured = False
    install_commands = _install_command_templates(package_manager) if package_manager else []
    requires_privilege_escalation = any(command.startswith("sudo ") for command in install_commands)
    user_space_probe: dict[str, Any] | None = None

    if not latex_engine:
        notes.append("No supported LaTeX engine found (latexmk/pdflatex/tectonic).")
    else:
        notes.append(f"Detected LaTeX engine: {latex_engine}")

    if not sandbox_tool:
        notes.append("No supported sandbox tool found (bwrap/firejail/nsjail).")
    else:
        notes.append(f"Detected sandbox tool: {sandbox_tool}")

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
        wrapper = ensure_sandbox_wrapper(cwd)
        if wrapper:
            wrapper_path = f'["{wrapper}"]'
            auto_configured = True
            notes.append(f"Auto-configured sandbox wrapper: {wrapper}")

    if not wrapper_path:
        notes.append("Sandbox wrapper command is not configured.")
    if bootstrap_script_path:
        notes.append(f"Bootstrap script available: {bootstrap_script_path}")
    if requires_privilege_escalation and not _sudo_usable():
        notes.append("Install commands likely require elevated privileges and passwordless sudo is not available.")

    ready = bool(latex_engine and wrapper_path)
    return CompileEnvironmentReport(
        latex_engine=latex_engine,
        sandbox_tool=sandbox_tool,
        sandbox_wrapper_path=wrapper_path,
        auto_configured_wrapper=auto_configured,
        ready_for_compile=ready,
        package_manager=package_manager,
        bootstrap_script_path=bootstrap_script_path,
        install_commands=install_commands,
        requires_privilege_escalation=requires_privilege_escalation,
        cargo_path=cargo_path,
        pkg_config_path=pkg_config_path,
        user_space_probe=user_space_probe,
        notes=notes,
    )
