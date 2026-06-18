from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import write_json
from paperorchestra.core.session import artifact_path, load_session
from paperorchestra.orchestra.figure_core import (
    FIGURE_GATE_REPORT_FILENAME,
    FigureGatePolicy,
    FigureGateReport,
    FigureInventory,
    inventory_figure_assets,
)
from paperorchestra.orchestra.figure_generated import generated_figure_availability_from_plot_assets
from paperorchestra.orchestra.figure_slots import derive_figure_slots


def figure_gate_report_path(cwd: str | Path | None = None) -> Path:
    return artifact_path(cwd, FIGURE_GATE_REPORT_FILENAME)


def _session_paths(cwd: str | Path | None) -> tuple[str | None, str | None, str | None, str | None] | None:
    try:
        state = load_session(cwd)
    except FileNotFoundError:
        return None
    return (
        state.inputs.figures_dir,
        state.artifacts.plot_assets_json,
        state.artifacts.plot_manifest_json,
        state.artifacts.plot_captions_json,
    )


def _blocking_reasons(decisions: list[Any]) -> list[str]:
    reasons: list[str] = []
    for decision in decisions:
        if decision.status == "missing":
            reasons.extend(["figure_asset_missing", "placeholder_figure_unresolved"])
        elif decision.status == "ambiguous":
            reasons.extend(["ambiguous_figure_match", "placeholder_figure_unresolved"])
        elif decision.status == "human_finalization_needed":
            reasons.append("placeholder_figure_unresolved")
    return list(dict.fromkeys(reasons))


def build_figure_gate_report(
    cwd: str | Path | None = None,
    *,
    figures_dir: str | Path | None = None,
    plot_assets_path: str | Path | None = None,
    plot_manifest_path: str | Path | None = None,
    plot_captions_path: str | Path | None = None,
    policy: Any | None = None,
) -> dict[str, Any]:
    session_paths = _session_paths(cwd)
    if session_paths is not None:
        session_figures_dir, session_plot_assets_path, session_plot_manifest_path, session_plot_captions_path = session_paths
        figures_dir = figures_dir or session_figures_dir
        plot_assets_path = plot_assets_path or session_plot_assets_path
        plot_manifest_path = plot_manifest_path or session_plot_manifest_path
        plot_captions_path = plot_captions_path or session_plot_captions_path

    if not any([plot_assets_path, plot_manifest_path, plot_captions_path]):
        raise ValueError(
            "figure slot sources missing: provide --plot-assets/--plot-manifest/--plot-captions or run inside an initialized session"
        )

    slots = derive_figure_slots(
        plot_assets_path=plot_assets_path,
        plot_manifest_path=plot_manifest_path,
        plot_captions_path=plot_captions_path,
    )
    inventory = inventory_figure_assets(figures_dir) if figures_dir else FigureInventory()
    if not slots:
        payload = FigureGateReport(status="pass", decisions=[]).to_public_dict()
        payload["inventory"] = inventory.to_public_dict()
        return payload

    generated_assets = generated_figure_availability_from_plot_assets(cwd=cwd, plot_assets_path=plot_assets_path)
    matching_policy = policy if policy is not None else FigureGatePolicy()
    decisions = [matching_policy.match_slot(slot, inventory.assets, generated_assets) for slot in slots]
    blocking_reasons = _blocking_reasons(decisions)
    report = FigureGateReport(
        status="pass" if not blocking_reasons else "blocked",
        decisions=decisions,
        blocking_reasons=blocking_reasons,
    )
    payload = report.to_public_dict()
    payload["inventory"] = inventory.to_public_dict()
    payload["slot_count"] = len(slots)
    return payload


def write_figure_gate_report(
    cwd: str | Path | None = None,
    *,
    output_path: str | Path | None = None,
    figures_dir: str | Path | None = None,
    plot_assets_path: str | Path | None = None,
    plot_manifest_path: str | Path | None = None,
    plot_captions_path: str | Path | None = None,
    policy: Any | None = None,
) -> tuple[Path, dict[str, Any]]:
    payload = build_figure_gate_report(
        cwd,
        figures_dir=figures_dir,
        plot_assets_path=plot_assets_path,
        plot_manifest_path=plot_manifest_path,
        plot_captions_path=plot_captions_path,
        policy=policy,
    )
    path = Path(output_path).resolve() if output_path else figure_gate_report_path(cwd)
    write_json(path, payload)
    return path, payload
