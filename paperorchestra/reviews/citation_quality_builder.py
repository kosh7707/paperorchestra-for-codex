from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.session import load_session
from paperorchestra.loop_engine.quality.utils import _file_sha256
from paperorchestra.reviews import citation_quality_report as quality_report
from paperorchestra.reviews.citation_quality_counts import _counts, _empty_counts, _integrity_warning_codes
from paperorchestra.reviews.citation_quality_items_builder import _citation_quality_items, _quality_items_for_key
from paperorchestra.reviews.citation_quality_report import CitationQualityGateReport
from paperorchestra.reviews.citation_quality_sources import _citation_quality_source_paths, _citation_quality_sources, _stale_codes


def build_citation_quality_gate(cwd: str | Path | None, *, quality_mode: str = "ralph") -> dict[str, Any]:
    return build_citation_quality_gate_internal(cwd, quality_mode=quality_mode)["public_report"]


def build_citation_quality_gate_internal(cwd: str | Path | None, *, quality_mode: str = "ralph") -> dict[str, Any]:
    mode = _normalize_quality_mode(quality_mode)
    state = load_session(cwd)
    paper = Path(state.artifacts.paper_full_tex).resolve() if state.artifacts.paper_full_tex else None
    if paper is None or not paper.exists():
        return _missing_manuscript_payload(mode)

    manuscript_sha = _file_sha256(paper)
    paths = _citation_quality_source_paths(cwd, paper)
    sources = _citation_quality_sources(state, paths)
    hard = _stale_codes(
        {
            "rendered_reference_audit": sources["rendered"],
            "citation_source_match": sources["source_match"],
            "citation_integrity_audit": sources["integrity"],
        },
        manuscript_sha,
        claim_safe=mode == "claim_safe",
    )
    items, item_hard, item_warnings = _citation_quality_items(
        mode=mode,
        sources=sources,
        support_run_root=paths["citation_support_review"].parent.parent,
    )
    hard.extend(item_hard)
    warnings = item_warnings + _integrity_warning_codes(sources["integrity"])
    report = CitationQualityGateReport(
        status="fail" if sorted(dict.fromkeys(hard)) else "warn" if sorted(dict.fromkeys(warnings)) else "pass",
        quality_mode=mode,
        manuscript_sha256=manuscript_sha,
        hard_gate_failures=sorted(dict.fromkeys(hard)),
        warning_codes=sorted(dict.fromkeys(warnings)),
        counts=_counts(items, sources["integrity"]),
        items=items,
        source_artifact_hashes={name: _file_sha256(path) for name, path in paths.items()},
    )
    payload = report.to_internal_dict()
    quality_report._assert_public_safe(payload["public_report"])
    return payload


def _missing_manuscript_payload(mode: str) -> dict[str, Any]:
    report = CitationQualityGateReport(
        status="fail",
        quality_mode=mode,
        manuscript_sha256=None,
        hard_gate_failures=["citation_quality_manuscript_missing"],
        warning_codes=[],
        counts=_empty_counts(),
        source_artifact_hashes={},
    )
    payload = report.to_internal_dict()
    quality_report._assert_public_safe(payload["public_report"])
    return payload


def _normalize_quality_mode(value: str) -> str:
    return value if value in {"draft", "ralph", "claim_safe"} else "ralph"


__all__ = [
    "_citation_quality_items",
    "_citation_quality_source_paths",
    "_citation_quality_sources",
    "_missing_manuscript_payload",
    "_normalize_quality_mode",
    "_quality_items_for_key",
    "_stale_codes",
    "build_citation_quality_gate",
    "build_citation_quality_gate_internal",
]
