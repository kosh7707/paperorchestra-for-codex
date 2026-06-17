from __future__ import annotations

import os
import subprocess
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
SANDBOX_TOOLS = ["bwrap", "firejail", "nsjail"]
PACKAGE_MANAGERS = ["apt-get", "dnf", "yum", "pacman", "brew", "apk"]


def detect_latex_engine() -> str | None:
    for engine in LATEX_ENGINES:
        path = shutil.which(engine)
        if path:
            return path
    return None


def detect_sandbox_tool() -> str | None:
    return _detect_sandbox_tool_with_notes()[0]


def _command_text(command: list[str]) -> str:
    return " ".join(command)


def _trim_probe_output(text: str, *, limit: int = 240) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 3]}..."


def _sandbox_probe_command(tool_path: str) -> list[str]:
    tool_name = Path(tool_path).name
    if tool_name == "bwrap":
        command = [
            tool_path,
            "--unshare-all",
            "--share-net",
            "--die-with-parent",
            "--ro-bind",
            "/usr",
            "/usr",
            "--ro-bind",
            "/bin",
            "/bin",
        ]
        if Path("/lib").exists():
            command.extend(["--ro-bind", "/lib", "/lib"])
        if Path("/lib64").exists():
            command.extend(["--ro-bind", "/lib64", "/lib64"])
        command.extend(["--proc", "/proc", "--dev", "/dev", "/bin/true"])
        return command
    if tool_name == "firejail":
        return [tool_path, "--quiet", "--net=none", "--private", "/bin/true"]
    if tool_name == "nsjail":
        return [tool_path, "-Mo", "--chroot", "/", "--cwd", "/", "--disable_clone_newnet", "--", "/bin/true"]
    return [tool_path, "--help"]


def _sandbox_tool_usable(tool_path: str) -> tuple[bool, str]:
    command = _sandbox_probe_command(tool_path)
    try:
        proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=8, check=False)
    except subprocess.TimeoutExpired:
        return False, f"probe timed out: {_command_text(command)}"
    except OSError as exc:
        return False, f"probe could not start: {exc}"
    except Exception as exc:
        return False, f"probe raised {type(exc).__name__}: {exc}"

    output = _trim_probe_output("\n".join(part for part in (proc.stderr, proc.stdout) if part))
    if proc.returncode == 0:
        return True, f"probe passed: {_command_text(command)}"
    if output:
        return False, f"probe failed with exit {proc.returncode}: {output}"
    return False, f"probe failed with exit {proc.returncode}: {_command_text(command)}"


def _detect_sandbox_tool_with_notes() -> tuple[str | None, list[str]]:
    notes: list[str] = []
    for tool in SANDBOX_TOOLS:
        path = shutil.which(tool)
        if not path:
            continue
        usable, reason = _sandbox_tool_usable(path)
        if usable:
            notes.append(f"Detected usable sandbox tool: {path} ({reason})")
            return path, notes
        notes.append(f"Detected sandbox tool {path}, but it failed usability probe: {reason}")
    return None, notes


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


def _install_command_context() -> dict[str, Any]:
    is_root = hasattr(os, "geteuid") and os.geteuid() == 0
    sudo_path = shutil.which("sudo")
    sudo_usable = _sudo_usable()
    if is_root:
        prefix = ""
        can_run = True
    elif sudo_path:
        prefix = "sudo"
        can_run = sudo_usable
    else:
        prefix = None
        can_run = False
    return {
        "is_root": is_root,
        "sudo_available": bool(sudo_path),
        "sudo_usable": sudo_usable,
        "command_prefix": prefix or "",
        "can_run_install_commands_directly": can_run,
    }


def _with_prefix(command: str, prefix: str | None) -> str:
    return f"{prefix} {command}" if prefix else command


def _install_command_templates(package_manager_path: str, install_context: dict[str, Any] | None = None) -> list[str]:
    install_context = install_context or _install_command_context()
    tool = Path(package_manager_path).name
    if tool == "brew":
        return [
            "brew install --cask mactex-no-gui || brew install basictex",
            "brew install latexmk",
        ]
    if not install_context.get("is_root") and not install_context.get("sudo_available"):
        return []
    prefix = install_context.get("command_prefix") or ""
    if tool == "apt-get":
        return [
            _with_prefix("apt-get update", prefix),
            _with_prefix(
                "apt-get install -y pkg-config libpng-dev texlive-latex-base texlive-latex-recommended texlive-fonts-recommended latexmk bubblewrap",
                prefix,
            ),
        ]
    if tool == "dnf":
        return [
            _with_prefix("dnf install -y texlive-latex texlive-collection-latexrecommended latexmk bubblewrap", prefix),
        ]
    if tool == "yum":
        return [
            _with_prefix("yum install -y texlive texlive-latex latexmk bubblewrap", prefix),
        ]
    if tool == "pacman":
        return [
            _with_prefix("pacman -Sy --noconfirm texlive-latexextra texlive-fontsextra texlive-bin latexmk bubblewrap", prefix),
        ]
    if tool == "apk":
        return [
            _with_prefix("apk add texmf-dist texlive texlive-latexextra bubblewrap", prefix),
        ]
    return []


def _bootstrap_script_contents(package_manager_path: str) -> str:
    context = _install_command_context()
    commands = _install_command_templates(package_manager_path, context)
    if commands:
        body = "\n".join(commands)
    elif package_manager_path and not context.get("is_root") and not context.get("sudo_available"):
        body = 'echo "Compile bootstrap requires root privileges or sudo; rerun as root or install sudo/use your system package manager." >&2\nexit 1'
    else:
        body = 'echo "No known install recipe for this package manager." >&2\nexit 1'
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
        wrapper = ensure_sandbox_wrapper(cwd)
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
