from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_HIGH_SIGNAL_STOPWORDS = {
    "figure",
    "plot",
    "panel",
    "overview",
    "result",
    "results",
    "analysis",
    "comparison",
    "performance",
    "benchmark",
    "experiment",
    "stage",
    "across",
    "system",
    "method",
    "data",
    "model",
    "show",
    "shows",
    "summarize",
    "summarizes",
    "summary",
    "visual",
    "asset",
    "workflow",
}


def _normalize_figure_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"^fig(?:ure)?[:_\-\s]+", "", text)
    text = Path(text).stem if "/" in text or "\\" in text or "." in Path(text).name else text
    return re.sub(r"[^a-z0-9]+", "", text)


def _high_signal_tokens(*values: Any) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", str(value or "").lower()):
            normalized = token.replace("_", "").replace("-", "")
            if normalized and normalized not in _HIGH_SIGNAL_STOPWORDS:
                tokens.add(normalized)
    return tokens
