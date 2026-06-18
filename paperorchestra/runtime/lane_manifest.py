from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json
from paperorchestra.core.models import utc_now_iso
from paperorchestra.core.session import artifact_path, load_session, save_session


@dataclass(frozen=True)
class LaneManifest:
    stage: str
    role: str
    runtime_mode: str
    lane_type: str
    owner: str
    status: str
    started_at: str
    completed_at: str | None
    input_artifacts: list[str]
    output_artifacts: list[str]
    team_name: str | None = None
    fallback_used: bool = False
    notes: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def lane_manifest_name(stage: str) -> str:
    return f"lane-manifest.{stage}.json"


def record_lane_manifest(
    cwd: str | Path | None,
    *,
    stage: str,
    role: str,
    runtime_mode: str,
    lane_type: str,
    owner: str,
    status: str,
    input_artifacts: list[str],
    output_artifacts: list[str],
    team_name: str | None = None,
    fallback_used: bool = False,
    notes: list[str] | None = None,
) -> Path:
    path = artifact_path(cwd, lane_manifest_name(stage))
    now = utc_now_iso()
    payload = LaneManifest(
        stage=stage,
        role=role,
        runtime_mode=runtime_mode,
        lane_type=lane_type,
        owner=owner,
        status=status,
        started_at=now,
        completed_at=now if status in {"completed", "fallback_completed", "blocked", "failed"} else None,
        input_artifacts=input_artifacts,
        output_artifacts=output_artifacts,
        team_name=team_name,
        fallback_used=fallback_used,
        notes=notes or [],
    )
    path.write_text(json.dumps(payload.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def collect_lane_manifests(cwd: str | Path | None) -> list[dict[str, Any]]:
    state = load_session(cwd)
    artifacts_dir = Path(state.artifacts.outline_json).parent if state.artifacts.outline_json else artifact_path(cwd, "placeholder").parent
    return [read_json(path) for path in sorted(artifacts_dir.glob("lane-manifest.*.json"))]


def build_lane_manifest_summary(cwd: str | Path | None) -> dict[str, Any]:
    manifests = collect_lane_manifests(cwd)
    by_stage: dict[str, dict[str, Any]] = {}
    fallback_count = 0
    runtime_modes: dict[str, int] = {}
    lane_types: dict[str, int] = {}
    for manifest in manifests:
        if not isinstance(manifest, dict):
            continue
        stage = str(manifest.get("stage") or f"unknown-{len(by_stage)+1}")
        fallback_used = bool(manifest.get("fallback_used"))
        runtime_mode = str(manifest.get("runtime_mode") or "unknown")
        lane_type = str(manifest.get("lane_type") or "unknown")
        if fallback_used:
            fallback_count += 1
        runtime_modes[runtime_mode] = runtime_modes.get(runtime_mode, 0) + 1
        lane_types[lane_type] = lane_types.get(lane_type, 0) + 1
        by_stage[stage] = {
            "status": manifest.get("status"),
            "runtime_mode": runtime_mode,
            "lane_type": lane_type,
            "fallback_used": fallback_used,
            "team_name": manifest.get("team_name"),
            "notes": manifest.get("notes") or [],
            "path_hint": lane_manifest_name(stage),
        }
    return {
        "manifest_count": len(manifests),
        "fallback_count": fallback_count,
        "runtime_mode_counts": runtime_modes,
        "lane_type_counts": lane_types,
        "stages": by_stage,
    }


def write_lane_manifest_summary(cwd: str | Path | None, *, name: str = "lane-manifest-summary.json") -> tuple[Path, dict[str, Any]]:
    payload = build_lane_manifest_summary(cwd)
    path = artifact_path(cwd, name)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    state = load_session(cwd)
    state.artifacts.latest_lane_summary_json = str(path)
    state.notes.append(f"Lane manifest summary recorded: {path.name}")
    save_session(cwd, state)
    return path, payload
