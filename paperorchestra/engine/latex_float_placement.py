from __future__ import annotations

import re


def _stabilize_figure_float_placement(latex: str) -> str:
    """Avoid top-only figure floats that LaTeX can defer to the manuscript tail."""

    def replace(match: re.Match[str]) -> str:
        env = match.group(1)
        placement = match.group(2)
        if placement is not None:
            normalized = placement.replace(" ", "")
            placement_flags = set(normalized.lower())
            if placement_flags & {"h", "b", "p"} or "H" in normalized:
                return match.group(0)
        stable = "!tbp" if env == "figure*" else "!htbp"
        return f"\\begin{{{env}}}[{stable}]"

    return re.sub(r"\\begin\{(figure\*?)\}(?:\[([^\]]*)\])?", replace, latex)
