from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _normalize_plot_context_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"^fig(?:ure)?[:_\-\s]+", "", text)
    text = Path(text).stem if "/" in text or "\\" in text or "." in Path(text).name else text
    return re.sub(r"[^a-z0-9]+", "", text)
