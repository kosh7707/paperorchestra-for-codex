from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.loop_engine.quality.utils import _read_json_if_exists
from paperorchestra.reviews.citation_integrity_paths import citation_integrity_audit_path, citation_source_match_path
from paperorchestra.reviews.citation_rendered_references import rendered_reference_audit_path


def _citation_quality_source_paths(cwd: str | Path | None, paper: Path) -> dict[str, Path]:
    return {
        "rendered_reference_audit": rendered_reference_audit_path(cwd),
        "citation_support_review": paper.parent / "citation_support_review.json",
        "citation_source_match": citation_source_match_path(cwd),
        "citation_integrity_audit": citation_integrity_audit_path(cwd),
    }


def _citation_quality_sources(state: Any, paths: dict[str, Path]) -> dict[str, Any]:
    return {
        "rendered": _read_json_if_exists(paths["rendered_reference_audit"]),
        "support": _read_json_if_exists(paths["citation_support_review"]),
        "source_match": _read_json_if_exists(paths["citation_source_match"]),
        "integrity": _read_json_if_exists(paths["citation_integrity_audit"]),
        "claim_map": _read_json_if_exists(state.artifacts.claim_map_json),
        "placement": _read_json_if_exists(state.artifacts.citation_placement_plan_json),
    }


def _stale_codes(payloads: dict[str, Any], manuscript_sha: str | None, *, claim_safe: bool) -> list[str]:
    if not claim_safe or not manuscript_sha:
        return []
    stale: list[str] = []
    for payload in payloads.values():
        if not isinstance(payload, dict):
            continue
        bound = payload.get("manuscript_sha256") or payload.get("paper_full_tex_sha256")
        if bound and bound != manuscript_sha:
            stale.append("citation_quality_stale")
    return sorted(dict.fromkeys(stale))
