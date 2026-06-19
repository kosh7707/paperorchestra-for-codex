from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import write_json
from paperorchestra.core.session import artifact_path, load_session
from paperorchestra.loop_engine.quality.high_risk_claim_sweep import _high_risk_claim_sweep
from paperorchestra.loop_engine.ralph.repair_recheck_baseline import _canonical_high_risk_baseline
from paperorchestra.loop_engine.ralph.repair_recheck_metrics import (
    _citation_integrity_metrics,
    _citation_issue_metrics_from_packet,
    _file_sha256,
    _high_risk_issue_metrics_from_packet,
    _high_risk_metrics,
    _strictly_improves,
)
from paperorchestra.loop_engine.ralph.state import _read_json
from paperorchestra.manuscript.source_obligation_eval import evaluate_source_obligations
from paperorchestra.reviews.citation_integrity_audit import build_citation_integrity_audit


def _candidate_semantic_recheck(
    cwd: str | Path | None,
    *,
    claim_safety_issues: list[dict[str, Any]],
    quality_mode: str = "claim_safe",
    original_manuscript_hash: str | None = None,
) -> dict[str, Any]:
    citation_targeted = any(
        str(item.get("issue_type") or "").startswith("citation_bomb_")
        or item.get("issue_type") == "citation_duplicate_support"
        for item in claim_safety_issues
    )
    high_risk_targeted = any(item.get("issue_type") == "high_risk_uncited_claim" for item in claim_safety_issues)

    canonical_citation_path = artifact_path(cwd, "citation_integrity.audit.json")
    try:
        canonical_citation = _read_json(canonical_citation_path)
    except Exception:
        canonical_citation = {}
    citation_before = (
        _citation_integrity_metrics(canonical_citation)
        if isinstance(canonical_citation, dict) and canonical_citation
        else _citation_issue_metrics_from_packet(claim_safety_issues)
    )
    citation_after_payload = build_citation_integrity_audit(cwd, quality_mode=quality_mode)
    citation_after = _citation_integrity_metrics(citation_after_payload)
    citation_path = artifact_path(cwd, "citation-integrity.citation-repair.candidate.json")
    write_json(citation_path, citation_after_payload)

    high_risk_before, high_risk_baseline_source = _canonical_high_risk_baseline(
        cwd,
        original_manuscript_hash=original_manuscript_hash,
    )
    if high_risk_before is None:
        high_risk_before = _high_risk_issue_metrics_from_packet(claim_safety_issues)
        if high_risk_baseline_source in {"quality_eval_missing", "quality_eval_high_risk_missing"}:
            high_risk_baseline_source = "repair_packet"
    high_risk_after_payload = _high_risk_claim_sweep(load_session(cwd), evaluate_source_obligations(cwd))
    high_risk_after = _high_risk_metrics(high_risk_after_payload)
    high_risk_path = artifact_path(cwd, "high-risk-sweep.citation-repair.candidate.json")
    write_json(high_risk_path, high_risk_after_payload)

    citation_improved = (not citation_targeted) or _strictly_improves(
        int(citation_before.get("target_issue_count") or 0),
        int(citation_after.get("target_issue_count") or 0),
    )
    high_risk_improved = (not high_risk_targeted) or _strictly_improves(
        int(high_risk_before.get("item_count") or 0),
        int(high_risk_after.get("item_count") or 0),
    )
    status = "pass" if citation_improved and high_risk_improved else "fail"
    return {
        "status": status,
        "citation_integrity": {
            "targeted": citation_targeted,
            "path": str(citation_path),
            "sha256": _file_sha256(citation_path),
            "before": citation_before,
            "after": citation_after,
            "improved": citation_improved,
        },
        "high_risk_claim_sweep": {
            "targeted": high_risk_targeted,
            "baseline_source": high_risk_baseline_source,
            "path": str(high_risk_path),
            "sha256": _file_sha256(high_risk_path),
            "before": high_risk_before,
            "after": high_risk_after,
            "improved": high_risk_improved,
        },
    }
