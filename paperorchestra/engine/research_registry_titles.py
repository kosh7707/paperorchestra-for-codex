from __future__ import annotations

import re

from paperorchestra.core.models import VerifiedPaper


def normalized_registry_title_key(paper: VerifiedPaper) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", paper.title.lower())).strip()
