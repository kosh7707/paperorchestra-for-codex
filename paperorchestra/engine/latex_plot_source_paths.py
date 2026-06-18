from __future__ import annotations

import re
from pathlib import Path


def _normalize_source_figure_paths(latex: str, figures_dir: str | None) -> str:
    if not figures_dir:
        return latex
    path = Path(figures_dir)
    if not path.exists():
        return latex
    for figure_path in sorted(path.iterdir()):
        if figure_path.is_file():
            latex = _normalize_source_figure_path(latex, figure_path.name)
    return latex.replace("inputs/inputs/figures/", "inputs/figures/")


def _normalize_source_figure_path(latex: str, name: str) -> str:
    normalized = f"inputs/figures/{name}"
    for prefix in ["figures", "figs"]:
        latex = re.sub(rf"(?<!inputs/){re.escape(prefix)}/{re.escape(name)}", normalized, latex)
        latex = re.sub(rf"(?<!inputs\\){re.escape(prefix)}\\{re.escape(name)}", normalized, latex)
    return re.sub(
        rf"(\\includegraphics(?:\[[^\]]*\])?\{{)(?![^}}]*inputs/figures/){re.escape(name)}(\}})",
        lambda match: f"{match.group(1)}{normalized}{match.group(2)}",
        latex,
    )
