from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.orchestra.figure_core import (
    FIGURE_EXTENSIONS,
    FIGURE_GATE_REPORT_FILENAME,
    FIGURE_GATE_SCHEMA_VERSION,
    FigureAsset,
    FigureGatePolicy as _CoreFigureGatePolicy,
    FigureGateReport,
    FigureInventory,
    FigureMatchDecision,
    FigureSlot,
    GeneratedFigureAvailability,
    inventory_figure_assets,
)
from paperorchestra.orchestra.figure_reports import (
    derive_figure_slots,
    figure_gate_report_path,
    build_figure_gate_report as _build_figure_gate_report,
    write_figure_gate_report as _write_figure_gate_report,
)


class FigureGatePolicy(_CoreFigureGatePolicy):
    def apply_to_state(self, state: Any) -> Any:
        from paperorchestra.orchestra.policies import ReadinessPolicy

        updated = state.clone()
        if updated.facets.figures == "placeholder_only" and "placeholder_figure_unresolved" not in updated.blocking_reasons:
            updated.blocking_reasons.append("placeholder_figure_unresolved")
        return ReadinessPolicy().apply(updated)


def build_figure_gate_report(
    cwd: str | Path | None = None,
    *,
    figures_dir: str | Path | None = None,
    plot_assets_path: str | Path | None = None,
    plot_manifest_path: str | Path | None = None,
    plot_captions_path: str | Path | None = None,
) -> dict[str, Any]:
    return _build_figure_gate_report(
        cwd,
        figures_dir=figures_dir,
        plot_assets_path=plot_assets_path,
        plot_manifest_path=plot_manifest_path,
        plot_captions_path=plot_captions_path,
        policy=FigureGatePolicy(),
    )


def write_figure_gate_report(
    cwd: str | Path | None = None,
    *,
    output_path: str | Path | None = None,
    figures_dir: str | Path | None = None,
    plot_assets_path: str | Path | None = None,
    plot_manifest_path: str | Path | None = None,
    plot_captions_path: str | Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    return _write_figure_gate_report(
        cwd,
        output_path=output_path,
        figures_dir=figures_dir,
        plot_assets_path=plot_assets_path,
        plot_manifest_path=plot_manifest_path,
        plot_captions_path=plot_captions_path,
        policy=FigureGatePolicy(),
    )
