from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from paperorchestra.orchestra.figure_core import GeneratedFigureAvailability, _sha256
from paperorchestra.orchestra.figure_slots import _read_json_if_exists


def _resolve_existing_plot_asset_path(raw_value: Any, *, bases: list[Path]) -> Path | None:
    if not isinstance(raw_value, str) or not raw_value.strip():
        return None
    candidate = Path(raw_value)
    if candidate.is_absolute():
        return candidate if candidate.exists() else None
    for base in bases:
        resolved = (base / candidate).resolve()
        if resolved.exists():
            return resolved
    return None


def generated_figure_availability_from_plot_assets(
    *,
    cwd: str | Path | None = None,
    plot_assets_path: str | Path | None = None,
) -> dict[str, GeneratedFigureAvailability]:
    payload = _read_json_if_exists(plot_assets_path)
    if not isinstance(payload, dict) or not plot_assets_path:
        return {}

    plot_assets_file = Path(plot_assets_path).resolve()
    bases = [plot_assets_file.parent]
    if cwd is not None:
        bases.insert(0, Path(cwd).resolve())

    available: dict[str, GeneratedFigureAvailability] = {}
    for item in payload.get("assets") or []:
        if not isinstance(item, dict):
            continue
        figure_id = item.get("figure_id") or item.get("id") or item.get("label")
        if not isinstance(figure_id, str) or not figure_id:
            continue
        asset_kind = item.get("asset_kind")
        review_status = item.get("review_status")
        if asset_kind != "generated_placeholder" and review_status != "human_final_artwork_required":
            continue
        existing_paths = [
            resolved
            for key in ("path", "tex_path", "latex_path", "latex_snippet_path")
            if (resolved := _resolve_existing_plot_asset_path(item.get(key), bases=bases)) is not None
        ]
        if not existing_paths:
            continue
        digest = hashlib.sha256()
        for path in sorted({path.resolve() for path in existing_paths}):
            digest.update(path.name.encode("utf-8", errors="replace"))
            digest.update(b"\0")
            digest.update(_sha256(path).encode("ascii"))
            digest.update(b"\0")
        reasons = ["generated_asset_available"]
        if asset_kind == "generated_placeholder":
            reasons.append("generated_placeholder")
        if review_status == "human_final_artwork_required":
            reasons.append("human_final_artwork_required")
        available[figure_id] = GeneratedFigureAvailability(
            figure_id=figure_id,
            sha256=digest.hexdigest(),
            reasons=tuple(dict.fromkeys(reasons)),
        )
    return available
