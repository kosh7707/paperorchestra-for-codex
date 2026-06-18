from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.session import artifact_path
from paperorchestra.loop_engine.quality.utils import _read_json_if_exists
from paperorchestra.reviews.citation_support_v3 import _support_items_from_v3_cases


def _citation_support_review_path(cwd: str | Path | None, state: Any) -> Path:
    if state.artifacts.paper_full_tex:
        return Path(state.artifacts.paper_full_tex).resolve().parent / "citation_support_review.json"
    return artifact_path(cwd, "citation_support_review.json")


def _support_items(cwd: str | Path | None, state: Any) -> list[dict[str, Any]]:
    support_path = _citation_support_review_path(cwd, state)
    payload = _read_json_if_exists(support_path)
    if isinstance(payload, dict) and payload.get("schema") == "citation-support-review/3":
        return _support_items_from_v3_cases(payload.get("cases"), run_root=support_path.parent.parent)
    items = payload.get("items") if isinstance(payload, dict) else None
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []
