from __future__ import annotations

import json
from pathlib import Path

from paperorchestra.core.session import set_current_session
from paperorchestra.engine import plot_stages


def _plot_payload() -> dict:
    return {
        "figures": [
            {
                "figure_id": "fig-1",
                "title": "Architecture Overview",
                "plot_type": "diagram",
                "data_source": "design notes",
                "objective": "Show the pipeline",
                "aspect_ratio": "16:9",
                "rendering_brief": "Layered boxes",
                "caption": "The pipeline components and their artifact flow.",
                "source_fidelity_notes": "Derived from design notes.",
            }
        ]
    }


def test_write_plot_artifacts_and_generated_assets(tmp_path: Path) -> None:
    set_current_session(tmp_path, "test-session")

    manifest_path, captions_path = plot_stages._write_plot_artifacts(tmp_path, _plot_payload())
    assets_dir, index_path = plot_stages._write_plot_assets(tmp_path, _plot_payload())

    assert manifest_path.name == "plot_manifest.json"
    assert captions_path.name == "plot_captions.json"
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["figures"][0]["figure_id"] == "fig-1"
    assert json.loads(captions_path.read_text(encoding="utf-8")) == {
        "fig-1": "The pipeline components and their artifact flow."
    }
    assert assets_dir.name == "plot-assets"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert index["assets"][0]["filename"] == "fig-1.svg"
    assert (assets_dir / "fig-1.svg").exists()
    assert (assets_dir / "fig-1.tex").exists()
