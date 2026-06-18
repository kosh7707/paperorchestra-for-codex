from __future__ import annotations

from pathlib import Path
import sys
from typing import Any


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PACKAGE_ROOT.parent


def package_context(cwd: str | Path | None = None) -> dict[str, Any]:
    """Return import/install context useful for diagnosing stale installs."""

    root = Path(cwd or ".").resolve()
    stale_warning = None
    if (root / "pyproject.toml").exists() and PROJECT_ROOT != root:
        stale_warning = (
            "The imported paperorchestra package is not from the current working "
            "tree. Activate the repo .venv or run `python -m pip install -e .` "
            "from this checkout."
        )
    return {
        "cwd": str(root),
        "project_root": str(PROJECT_ROOT),
        "package_root": str(PACKAGE_ROOT),
        "package_file": str(PACKAGE_ROOT / "__init__.py"),
        "python_executable": sys.executable,
        "stale_install_warning": stale_warning,
    }
