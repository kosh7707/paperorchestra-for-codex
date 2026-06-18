from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.session import artifact_path
from paperorchestra.reviews.reproducibility_artifacts import _read_json_if_exists
from paperorchestra.reviews.reproducibility_citation_surface import _citation_surface_health


def _citation_support_review_provenance(cwd: str | Path | None, state, session_artifact_dir: Path | None) -> dict[str, Any]:
    candidates: list[Path] = [artifact_path(cwd, "citation_support_review.json")]
    if session_artifact_dir is not None:
        candidates.append(session_artifact_dir / "citation_support_review.json")
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        payload = _read_json_if_exists(candidate)
        if not isinstance(payload, dict):
            continue
        provenance = payload.get("evidence_provenance") if isinstance(payload.get("evidence_provenance"), dict) else {}
        mode = str(payload.get("review_mode") or provenance.get("mode") or "")
        provider_name = provenance.get("provider_name")
        model_review_used = bool(provenance.get("model_review_used"))
        live = mode in {"model", "web"} and model_review_used and provider_name != "mock"
        return {
            "status": "present",
            "path": str(candidate),
            "mode": mode,
            "provider_name": provider_name,
            "web_search_required": bool(provenance.get("web_search_required")),
            "model_review_used": model_review_used,
            "semantic_scholar_required": bool(provenance.get("semantic_scholar_required")),
            "live": live,
        }
    return {"status": "missing", "path": str(candidates[0]), "live": False, "semantic_scholar_required": False}
