from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.runtime.environment_context import PROJECT_ROOT, package_context
from paperorchestra.runtime.environment_variables import grouped_environment_variables


def environment_guide_path() -> Path:
    return PROJECT_ROOT / "README.md"


def env_example_path() -> Path:
    return PROJECT_ROOT / "README.md"


def build_environment_inventory() -> dict[str, Any]:
    return {
        "package_context": package_context(),
        "docs": {
            "environment_guide": str(environment_guide_path()),
            "env_example": str(env_example_path()),
        },
        "python": {
            "requires_python": ">=3.11",
            "python_dependencies": [],
            "install_command": "python3 -m venv .venv && . .venv/bin/activate && python -m pip install -e .",
            "direct_pip_note": "On externally managed Python installs, use a virtual environment instead of system pip.",
        },
        "prerequisites": {
            "basic_operation": ["Python 3.11+", "venv-local editable install of this checkout"],
            "shell_provider": ["Set PAPERO_MODEL_CMD to a compatible executable (for example Codex CLI)."],
            "omx_native": ["omx", "codex"],
            "compile": {
                "latex_engines": ["latexmk", "pdflatex", "tectonic"],
                "sandbox_tools": ["bwrap", "firejail", "nsjail"],
                "inspection_commands": [
                    "paperorchestra environment --summary",
                ],
            },
        },
        "groups": grouped_environment_variables(),
        "auto_managed_env": [
            {
                "name": "BIBINPUTS",
                "description": "Set automatically during compile runs so BibTeX can find the generated bibliography.",
            },
            {
                "name": "BSTINPUTS",
                "description": "Set automatically during compile runs so BibTeX can find custom .bst files.",
            },
        ],
    }
