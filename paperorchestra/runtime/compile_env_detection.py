from __future__ import annotations

import shutil

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


__all__ = [
    "LATEX_ENGINES",
    "PACKAGE_MANAGERS",
    "detect_cargo",
    "detect_latex_engine",
    "detect_package_manager",
    "detect_pkg_config",
]
