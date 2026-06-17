from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from paperorchestra.core.io import write_json
from paperorchestra.core.session import artifact_path, load_session
from paperorchestra.orchestra.figure_core import (
    FIGURE_GATE_REPORT_FILENAME,
    FigureGatePolicy,
    FigureGateReport,
    FigureInventory,
    FigureSlot,
    GeneratedFigureAvailability,
    _sha256,
    inventory_figure_assets,
)


def _read_json_if_exists(path: str | Path | None) -> Any:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists():
        return None
    return json.loads(candidate.read_text(encoding="utf-8"))


def figure_gate_report_path(cwd: str | Path | None = None) -> Path:
    return artifact_path(cwd, FIGURE_GATE_REPORT_FILENAME)


def _slot_from_mapping(item: dict[str, Any], *, fallback_index: int, default_placeholder: bool) -> FigureSlot | None:
    identifier = item.get("figure_id") or item.get("id") or item.get("label") or item.get("filename") or f"figure_slot_{fallback_index}"
    purpose = item.get("purpose") or item.get("caption") or item.get("title") or item.get("description") or identifier
    placeholder_value = item.get("placeholder")
    if placeholder_value is None:
        placeholder = bool(
            default_placeholder
            or item.get("asset_kind") == "generated_placeholder"
            or item.get("review_status") == "human_final_artwork_required"
        )
    else:
        placeholder = bool(placeholder_value)
    if not isinstance(identifier, str) or not isinstance(purpose, str):
        return None
    return FigureSlot(slot_id=identifier, purpose=purpose, placeholder=placeholder)


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


def _generated_figure_availability_from_plot_assets(
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
        existing_paths: list[Path] = []
        for key in ("path", "tex_path", "latex_path", "latex_snippet_path"):
            resolved = _resolve_existing_plot_asset_path(item.get(key), bases=bases)
            if resolved is not None:
                existing_paths.append(resolved)
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


def derive_figure_slots(
    *,
    plot_assets_path: str | Path | None = None,
    plot_manifest_path: str | Path | None = None,
    plot_captions_path: str | Path | None = None,
) -> list[FigureSlot]:
    slots: list[FigureSlot] = []
    seen: set[str] = set()

    def append(slot: FigureSlot | None) -> None:
        if slot is None:
            return
        key = slot.slot_id
        if key in seen:
            return
        seen.add(key)
        slots.append(slot)

    assets_payload = _read_json_if_exists(plot_assets_path)
    if isinstance(assets_payload, dict):
        for index, item in enumerate(assets_payload.get("assets") or [], start=1):
            if not isinstance(item, dict):
                continue
            if item.get("asset_kind") == "generated_placeholder" or item.get("review_status") == "human_final_artwork_required":
                append(_slot_from_mapping(item, fallback_index=index, default_placeholder=True))

    manifest_payload = _read_json_if_exists(plot_manifest_path)
    if isinstance(manifest_payload, dict):
        for index, item in enumerate(manifest_payload.get("figures") or [], start=1):
            if isinstance(item, dict):
                append(_slot_from_mapping(item, fallback_index=index, default_placeholder=False))

    captions_payload = _read_json_if_exists(plot_captions_path)
    if isinstance(captions_payload, dict):
        values = captions_payload.get("captions") if isinstance(captions_payload.get("captions"), list) else captions_payload.get("figures")
        for index, item in enumerate(values or [], start=1):
            if isinstance(item, dict):
                append(_slot_from_mapping(item, fallback_index=index, default_placeholder=True))
        if values is None:
            for index, (identifier, caption) in enumerate(captions_payload.items(), start=1):
                if isinstance(identifier, str) and isinstance(caption, str):
                    append(
                        FigureSlot(
                            slot_id=identifier,
                            purpose=caption,
                            placeholder=True,
                        )
                    )

    return slots


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
    if not slots:
        report = FigureGateReport(status="pass", decisions=[], blocking_reasons=[])
        payload = report.to_public_dict()
        payload["inventory"] = FigureInventory().to_public_dict()
        return payload

    inventory = inventory_figure_assets(figures_dir) if figures_dir else FigureInventory()
    generated_assets = _generated_figure_availability_from_plot_assets(cwd=cwd, plot_assets_path=plot_assets_path)
    matching_policy = policy if policy is not None else FigureGatePolicy()
    decisions = [matching_policy.match_slot(slot, inventory.assets, generated_assets) for slot in slots]
    blocking_reasons: list[str] = []
    for decision in decisions:
        if decision.status == "missing":
            blocking_reasons.extend(["figure_asset_missing", "placeholder_figure_unresolved"])
        elif decision.status == "ambiguous":
            blocking_reasons.extend(["ambiguous_figure_match", "placeholder_figure_unresolved"])
        elif decision.status == "human_finalization_needed":
            blocking_reasons.append("placeholder_figure_unresolved")
    status = "pass" if not blocking_reasons else "blocked"
    report = FigureGateReport(status=status, decisions=decisions, blocking_reasons=list(dict.fromkeys(blocking_reasons)))
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
