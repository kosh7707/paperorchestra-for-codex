from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json, write_json
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


LOOP_REQUIRED_STATUSES = {"matched", "generated_asset_available", "already_realized"}
LOOP_ACCEPTED_VERDICTS = {"pass", "passed", "accepted", "approve", "approved", "ok", "non_blocking", "non-blocking"}
LOOP_BLOCKING_VERDICTS = {"fail", "failed", "block", "blocked", "reject", "rejected", "revise", "human_needed"}
REQUIRED_FIGURE_VISUAL_CHECKS = ("ai_artifact_check", "publication_figure_check")


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



def _safe_artifact_stem(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip(".-")
    return normalized or "figure"


def _artifact_search_dirs(
    cwd: str | Path | None,
    *source_paths: str | Path | None,
) -> list[Path]:
    dirs: list[Path] = []

    def add(candidate: Path | None) -> None:
        if candidate is None:
            return
        resolved = candidate.resolve()
        if resolved not in dirs:
            dirs.append(resolved)

    if cwd is not None:
        root = Path(cwd).resolve()
        add(root)
        add(root / "figures")
        add(root / "artifacts")
    for raw in source_paths:
        if raw:
            add(Path(raw).resolve().parent)
    try:
        add(artifact_path(cwd, FIGURE_GATE_REPORT_FILENAME).parent)
    except Exception:
        pass
    return dirs


def _find_loop_artifact(search_dirs: list[Path], slot_id: str, *, prefix: str, suffix: str) -> Path | None:
    stems = list(dict.fromkeys([slot_id, _safe_artifact_stem(slot_id)]))
    names = [f"{prefix}.{stem}{suffix}" for stem in stems]
    for directory in search_dirs:
        for name in names:
            candidate = directory / name
            if candidate.exists():
                return candidate.resolve()
    return None


def _load_json_payload(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        payload = read_json(path)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _loop_verdict(payload: dict[str, Any] | None) -> str:
    if not isinstance(payload, dict):
        return "missing"
    return str(payload.get("verdict") or payload.get("status") or payload.get("decision") or "").strip().lower()


def _critic_artifact_status(path: Path | None) -> tuple[str, list[str]]:
    if path is None:
        return "missing", ["figure_critic_missing"]
    payload = _load_json_payload(path)
    if payload is None:
        return "blocked", ["figure_critic_unreadable"]
    verdict = _loop_verdict(payload)
    blocking_issues = payload.get("blocking_issues")
    has_blocking_issues = isinstance(blocking_issues, list) and bool(blocking_issues)
    if verdict in LOOP_ACCEPTED_VERDICTS and not has_blocking_issues:
        return "pass", []
    if verdict in LOOP_BLOCKING_VERDICTS or has_blocking_issues:
        return "blocked", ["figure_critic_blocking"]
    return "blocked", ["figure_critic_verdict_missing"]


def _finding_has_blocking_severity(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    severity = str(item.get("severity") or item.get("status") or item.get("verdict") or "").lower()
    return severity in {"fail", "failed", "error", "critical", "block", "blocked", "warn", "warning", "revise"}


def _visual_artifact_status(path: Path | None) -> tuple[str, list[str]]:
    if path is None:
        return "missing", ["figure_visual_findings_missing"]
    payload = _load_json_payload(path)
    if payload is None:
        return "blocked", ["figure_visual_findings_unreadable"]
    completed = payload.get("checks_completed") or payload.get("completed_visual_checks") or []
    completed_checks = {str(item).strip() for item in completed if str(item).strip()} if isinstance(completed, list) else set()
    missing_checks = [check for check in REQUIRED_FIGURE_VISUAL_CHECKS if check not in completed_checks]
    reasons: list[str] = []
    if missing_checks:
        reasons.append("figure_visual_checks_missing")
    verdict = _loop_verdict(payload)
    if verdict and verdict not in LOOP_ACCEPTED_VERDICTS:
        reasons.append("figure_visual_findings_blocking")
    if any(payload.get(key) for key in ("failing_codes", "warning_codes", "blocking_issues")):
        reasons.append("figure_visual_findings_blocking")
    for key in ("findings", "page_findings", "document_findings", "differences"):
        items = payload.get(key)
        if isinstance(items, list) and any(_finding_has_blocking_severity(item) for item in items):
            reasons.append("figure_visual_findings_blocking")
    if reasons:
        return "blocked", list(dict.fromkeys(reasons))
    if not verdict:
        return "blocked", ["figure_visual_verdict_missing"]
    return "pass", []


def _figure_loop_artifact_report(slots: list[Any], decisions: list[Any], search_dirs: list[Path]) -> dict[str, Any]:
    decisions_by_slot = {decision.slot_id: decision for decision in decisions}
    figure_reports: list[dict[str, Any]] = []
    blocking_reasons: list[str] = []
    for slot in slots:
        decision = decisions_by_slot.get(slot.slot_id)
        if decision is None or decision.status not in LOOP_REQUIRED_STATUSES:
            continue
        plan_path = _find_loop_artifact(search_dirs, slot.slot_id, prefix="figure-plan", suffix=".md")
        critic_path = _find_loop_artifact(search_dirs, slot.slot_id, prefix="figure-critic", suffix=".json")
        visual_path = _find_loop_artifact(search_dirs, slot.slot_id, prefix="figure-visual-findings", suffix=".json")
        slot_reasons: list[str] = []
        if plan_path is None:
            slot_reasons.append("figure_plan_missing")
        critic_status, critic_reasons = _critic_artifact_status(critic_path)
        visual_status, visual_reasons = _visual_artifact_status(visual_path)
        slot_reasons.extend(critic_reasons)
        slot_reasons.extend(visual_reasons)
        slot_reasons = list(dict.fromkeys(slot_reasons))
        if slot_reasons:
            blocking_reasons.append("figure_loop_artifact_missing")
            blocking_reasons.extend(slot_reasons)
        figure_reports.append(
            {
                "slot_id": slot.public_id(),
                "decision_status": decision.status,
                "status": "pass" if not slot_reasons else "blocked",
                "required_artifacts": {
                    "plan": str(plan_path) if plan_path else None,
                    "critic": str(critic_path) if critic_path else None,
                    "visual_findings": str(visual_path) if visual_path else None,
                },
                "critic_status": critic_status,
                "visual_status": visual_status,
                "blocking_reasons": slot_reasons,
            }
        )
    return {
        "schema_version": "figure-loop-artifacts/1",
        "required_for_statuses": sorted(LOOP_REQUIRED_STATUSES),
        "required_visual_checks": list(REQUIRED_FIGURE_VISUAL_CHECKS),
        "figures": figure_reports,
        "blocking_reasons": list(dict.fromkeys(blocking_reasons)),
        "status": "pass" if not blocking_reasons else "blocked",
    }


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
    search_dirs = _artifact_search_dirs(cwd, plot_assets_path, plot_manifest_path, plot_captions_path)
    loop_artifacts = _figure_loop_artifact_report(slots, decisions, search_dirs)
    blocking_reasons = _blocking_reasons(decisions)
    blocking_reasons.extend(loop_artifacts["blocking_reasons"])
    blocking_reasons = list(dict.fromkeys(blocking_reasons))
    report = FigureGateReport(
        status="pass" if not blocking_reasons else "blocked",
        decisions=decisions,
        blocking_reasons=blocking_reasons,
    )
    payload = report.to_public_dict()
    payload["inventory"] = inventory.to_public_dict()
    payload["slot_count"] = len(slots)
    payload["figure_loop_artifacts"] = loop_artifacts
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
