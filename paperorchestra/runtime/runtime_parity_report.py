from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.runtime.lane_manifest import collect_lane_manifests

REQUIRED_PARITY_STAGES = {
    "outline",
    "plot",
    "literature",
    "intro_related",
    "section_writing",
    "review",
    "refinement",
}
EXPECTED_PARITY_LANE_TYPES = {
    "outline": {"ralph"},
    "plot": {"team"},
    "literature": {"team"},
    "intro_related": {"ralph", "writer"},
    "section_writing": {"ralph", "writer"},
    "review": {"reviewer"},
    "refinement": {"refiner"},
}


def record_runtime_parity_report(
    cwd: str | Path | None,
    *,
    name: str = "runtime-parity.json",
    output_path: str | Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    manifests = collect_lane_manifests(cwd)
    manifest_map = _manifest_map(manifests)
    checks = [_parity_check(stage, manifest_map.get(stage)) for stage in sorted(REQUIRED_PARITY_STAGES)]
    overall = "implemented" if all(item["status"] == "implemented" for item in checks) else "partial"
    payload = {"overall_status": overall, "checks": checks, "manifest_count": len(manifests)}
    path = Path(output_path).resolve() if output_path else artifact_path(cwd, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    state = load_session(cwd)
    state.artifacts.latest_runtime_parity_json = str(path)
    state.notes.append(f"Runtime parity report recorded: {path.name}")
    save_session(cwd, state)
    return path, payload


def _manifest_map(manifests: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {item["stage"]: item for item in manifests if isinstance(item, dict) and "stage" in item}


def _parity_check(stage: str, manifest: dict[str, Any] | None) -> dict[str, str]:
    if not manifest:
        return {"stage": stage, "status": "missing", "reason": "no lane manifest recorded"}
    curated = _curated_literature_check(stage, manifest)
    if curated:
        return curated
    if manifest.get("runtime_mode") != "omx_native":
        return {"stage": stage, "status": "partial", "reason": "lane manifest exists but runtime_mode is not omx_native"}
    if manifest.get("fallback_used"):
        return {"stage": stage, "status": "partial", "reason": "stage used compatibility fallback instead of OMX-exclusive execution"}
    grounded = _grounded_literature_check(stage, manifest)
    if grounded:
        return grounded
    if manifest.get("lane_type") not in EXPECTED_PARITY_LANE_TYPES.get(stage, set()):
        return {"stage": stage, "status": "partial", "reason": f"lane_type {manifest.get('lane_type')} does not match expected OMX lane mapping"}
    return {"stage": stage, "status": "implemented", "reason": "OMX-native lane manifest recorded"}


def _curated_literature_check(stage: str, manifest: dict[str, Any]) -> dict[str, str] | None:
    if stage != "literature" or manifest.get("runtime_mode") != "curated_seed" or manifest.get("lane_type") != "manual":
        return None
    note_text = _note_text(manifest)
    if "curated prior-work entries" in note_text or "curated seed metadata" in note_text:
        return {
            "stage": stage,
            "status": "implemented",
            "reason": "curated prior-work import supplied the literature lane with explicit operator-provided source evidence",
        }
    return None


def _grounded_literature_check(stage: str, manifest: dict[str, Any]) -> dict[str, str] | None:
    if stage != "literature" or manifest.get("lane_type") != "python" or manifest.get("runtime_mode") != "omx_native":
        return None
    note_text = _note_text(manifest)
    if "grounded query completed" in note_text or "exact grounded seed preserved" in note_text:
        return {
            "stage": stage,
            "status": "implemented",
            "reason": "bounded grounded-discovery substitute executed under OMX-native control with recorded source evidence",
        }
    return None


def _note_text(manifest: dict[str, Any]) -> str:
    notes = manifest.get("notes") or []
    return "\n".join(note for note in notes if isinstance(note, str)).lower()
