from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.orchestra.figure_core import (
    FIGURE_EXTENSIONS,
    FIGURE_GATE_REPORT_FILENAME,
    FIGURE_GATE_SCHEMA_VERSION,
    _PRIVATE_MARKERS,
    _SAFE_SLOT_ID_RE,
    _STOPWORDS,
    FigureAsset,
    FigureGatePolicy as _CoreFigureGatePolicy,
    FigureGateReport,
    FigureInventory,
    FigureMatchDecision,
    FigureSlot,
    GeneratedFigureAvailability,
    _contains_private_marker,
    _decision_summary,
    _is_public_safe_identifier,
    _redacted_label,
    _sha256,
    _sha256_text,
    inventory_figure_assets,
)
from paperorchestra.orchestra.figure_reports import (
    _generated_figure_availability_from_plot_assets,
    _read_json_if_exists,
    _resolve_existing_plot_asset_path,
    _session_paths,
    _slot_from_mapping,
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
