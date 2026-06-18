from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


def _sudo_usable() -> bool:
    sudo = shutil.which("sudo")
    if not sudo:
        return False
    try:
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
        return [_with_prefix("dnf install -y texlive-latex texlive-collection-latexrecommended latexmk bubblewrap", prefix)]
    if tool == "yum":
        return [_with_prefix("yum install -y texlive texlive-latex latexmk bubblewrap", prefix)]
    if tool == "pacman":
        return [_with_prefix("pacman -Sy --noconfirm texlive-latexextra texlive-fontsextra texlive-bin latexmk bubblewrap", prefix)]
    if tool == "apk":
        return [_with_prefix("apk add texmf-dist texlive texlive-latexextra bubblewrap", prefix)]
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
