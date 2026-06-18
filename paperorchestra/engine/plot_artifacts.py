from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import write_json
from paperorchestra.core.session import artifact_path, build_path
from paperorchestra.engine.schemas import validate_plot_manifest
from paperorchestra.manuscript.plot_assets import render_plot_assets


def _write_plot_artifacts(cwd: str | Path | None, payload: dict[str, Any]) -> tuple[Path, Path]:
    validate_plot_manifest(payload)
    manifest_path = artifact_path(cwd, "plot_manifest.json")
    captions_path = artifact_path(cwd, "plot_captions.json")
    write_json(manifest_path, payload)
    write_json(captions_path, {item["figure_id"]: item["caption"] for item in payload["figures"]})
    return manifest_path, captions_path


def _write_plot_assets(cwd: str | Path | None, payload: dict[str, Any]) -> tuple[Path, Path]:
    assets_dir = build_path(cwd, "plot-assets")
    output_dir, index_path = render_plot_assets(payload, assets_dir)
    return output_dir, index_path
