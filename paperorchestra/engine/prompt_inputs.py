from __future__ import annotations

from pathlib import Path

from paperorchestra.core.io import read_text


def _read_inputs(state) -> dict[str, str]:
    return {
        "idea": read_text(state.inputs.idea_path),
        "experimental_log": read_text(state.inputs.experimental_log_path),
        "template": read_text(state.inputs.template_path),
        "guidelines": read_text(state.inputs.guidelines_path),
        "figures": _figure_listing(state.inputs.figures_dir),
    }


def _figure_listing(figures_dir: str | None) -> str:
    if not figures_dir:
        return "No figures directory provided."
    root = Path(figures_dir)
    if not root.exists():
        return f"Figures directory does not exist: {figures_dir}"
    files = [str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()]
    if not files:
        return "Figures directory is empty."
    return "\n".join(sorted(files))
