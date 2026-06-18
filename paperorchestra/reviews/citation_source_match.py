from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import write_json
from paperorchestra.core.session import load_session
from paperorchestra.loop_engine.quality.utils import _file_sha256, _read_json_if_exists
from paperorchestra.reviews.citation_integrity_paths import citation_source_match_path
from paperorchestra.reviews.citation_integrity_support import (
    _citation_support_review_path,
    _status_counts,
    _support_items,
)


def build_citation_source_match(cwd: str | Path | None, *, quality_mode: str = "ralph") -> dict[str, Any]:
    """Bind the citation support review into an explicit source-match artifact."""

    state = load_session(cwd)
    support_path = _citation_support_review_path(cwd, state)
    support = _read_json_if_exists(support_path)
    manuscript_sha = _file_sha256(state.artifacts.paper_full_tex)
    if not isinstance(support, dict):
        return {
            "schema_version": "citation-source-match/1",
            "status": "skipped",
            "quality_mode": quality_mode,
            "manuscript_sha256": manuscript_sha,
            "paper_full_tex_sha256": manuscript_sha,
            "citation_support_review": str(support_path),
            "citation_support_review_sha256": None,
            "reason": "citation_support_review_missing_or_unreadable",
            "items": [],
            "support_status_counts": {},
            "failing_codes": [],
        }
    items = _support_items(cwd, state)
    match_items: list[dict[str, Any]] = []
    failing_statuses = {"unsupported", "contradicted"}
    if quality_mode == "claim_safe":
        failing_statuses.update({"metadata_only", "insufficient_evidence"})
    for index, item in enumerate(items, start=1):
        status = str(item.get("support_status") or "unknown").strip().lower() or "unknown"
        evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
        match_items.append(
            {
                "id": str(item.get("id") or f"citation-support-{index}"),
                "sentence": item.get("sentence"),
                "citation_keys": [str(key) for key in item.get("citation_keys") or []],
                "support_status": status,
                "claim_type": item.get("claim_type"),
                "evidence_mode": support.get("evidence_mode"),
                "source_match_status": "fail" if status in failing_statuses else "pass",
                "evidence_count": len(evidence),
                "rationale": item.get("rationale") or item.get("reason") or item.get("explanation"),
            }
        )
    mismatch_ids = [str(item.get("id")) for item in match_items if item.get("source_match_status") == "fail"]
    failing = ["claim_source_mismatch"] if mismatch_ids else []
    return {
        "schema_version": "citation-source-match/1",
        "status": "fail" if mismatch_ids else "pass",
        "quality_mode": quality_mode,
        "manuscript_sha256": manuscript_sha,
        "paper_full_tex_sha256": manuscript_sha,
        "citation_support_review": str(support_path),
        "citation_support_review_sha256": _file_sha256(support_path),
        "evidence_mode": support.get("evidence_mode"),
        "support_status_counts": _status_counts(items),
        "failing_statuses": sorted(failing_statuses),
        "mismatch_item_ids": mismatch_ids,
        "items": match_items,
        "failing_codes": failing,
    }


def write_citation_source_match(
    cwd: str | Path | None,
    *,
    quality_mode: str = "ralph",
    output_path: str | Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    payload = build_citation_source_match(cwd, quality_mode=quality_mode)
    path = Path(output_path).resolve() if output_path else citation_source_match_path(cwd)
    write_json(path, payload)
    return path, payload
