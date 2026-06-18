from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json, write_json
from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.manuscript.narrative_contracts import planning_source_hashes
from paperorchestra.manuscript.narrative_payloads import build_planning_payloads


def write_planning_artifacts(cwd: str | Path | None) -> dict[str, Path]:
    narrative, claim_map, citation_plan = build_planning_payloads(cwd)
    narrative_path = artifact_path(cwd, "narrative_plan.json")
    claim_path = artifact_path(cwd, "claim_map.json")
    citation_path = artifact_path(cwd, "citation_placement_plan.json")
    write_json(narrative_path, narrative)
    write_json(claim_path, claim_map)
    write_json(citation_path, citation_plan)
    state = load_session(cwd)
    state.artifacts.narrative_plan_json = str(narrative_path)
    state.artifacts.claim_map_json = str(claim_path)
    state.artifacts.citation_placement_plan_json = str(citation_path)
    state.notes.append("Narrative/claim/citation placement planning artifacts recorded.")
    save_session(cwd, state)
    return {
        "narrative_plan": narrative_path,
        "claim_map": claim_path,
        "citation_placement_plan": citation_path,
    }


def planning_artifact_status(cwd: str | Path | None) -> dict[str, Any]:
    state = load_session(cwd)
    current_hashes = planning_source_hashes(cwd)
    artifacts = {
        "narrative_plan": state.artifacts.narrative_plan_json,
        "claim_map": state.artifacts.claim_map_json,
        "citation_placement_plan": state.artifacts.citation_placement_plan_json,
    }
    missing: list[str] = []
    stale: list[str] = []
    payloads: dict[str, dict[str, Any]] = {}
    for name, path in artifacts.items():
        if not path or not Path(path).exists():
            missing.append(f"{name}_missing")
            continue
        payload = read_json(path)
        payloads[name] = payload
        if payload.get("source_hashes") != current_hashes:
            stale.append(f"{name}_stale")
    return {
        "status": "fail" if missing or stale else "pass",
        "failing_codes": missing + stale,
        "source_hashes": current_hashes,
        "artifacts": artifacts,
        "payloads": payloads,
    }


def require_fresh_planning_artifacts(cwd: str | Path | None) -> None:
    status = planning_artifact_status(cwd)
    if status["status"] != "pass":
        raise RuntimeError(
            "Fresh narrative planning artifacts are required before writing. "
            "Run `paperorchestra run --provider shell` or `paperorchestra orchestrate --execute-local`. Failing codes: "
            + ", ".join(status["failing_codes"])
        )
