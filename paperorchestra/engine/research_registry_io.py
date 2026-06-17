from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json
from paperorchestra.core.models import VerifiedPaper


def load_prior_citation_registry(state: Any, *, note_prefix: str) -> list[VerifiedPaper]:
    registry_path = state.artifacts.citation_registry_json
    if not registry_path or not Path(registry_path).exists():
        return []
    try:
        prior_payload = read_json(registry_path)
        if isinstance(prior_payload, list):
            return [VerifiedPaper(**item) for item in prior_payload if isinstance(item, dict)]
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        state.notes.append(f"{note_prefix} and was treated as empty: {exc.__class__.__name__}.")
    return []
