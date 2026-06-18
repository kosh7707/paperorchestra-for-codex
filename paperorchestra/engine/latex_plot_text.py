from __future__ import annotations

import re


def _normalize_figure_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _escape_latex_text(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
    }
    return "".join(replacements.get(ch, ch) for ch in text)
