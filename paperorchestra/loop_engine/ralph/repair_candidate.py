from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.runtime.provider_base import BaseProvider


def build_repair_candidate(
    *,
    stage: Any,
    cwd: str | Path | None,
    provider: BaseProvider,
    runtime_mode: str,
    original: str,
    citation_map: dict[str, Any],
    issues: list[dict[str, Any]],
    claim_safety_issues: list[dict[str, Any]],
) -> tuple[str, dict[str, Any]]:
    system_prompt, user_prompt = stage._repair_prompt(
        original,
        stage.canonical_citation_map(citation_map),
        issues,
        claim_safety_issues,
        stage._source_obligation_repair_context(cwd),
    )
    response, lane_type, fallback_used, lane_notes = stage._complete_with_runtime_mode(
        stage._build_completion_request(system_prompt=system_prompt, user_prompt=user_prompt),
        provider=provider,
        runtime_mode=runtime_mode,
        cwd=cwd,
        omx_lane_type="ralph",
        trace_stage="citation_claim_repair",
    )
    candidate = stage.extract_latex(response)
    candidate, citation_replacements = stage.canonicalize_citation_keys(candidate, citation_map)
    unknown = sorted(set(stage.extract_citation_keys(candidate)) - stage.allowed_citation_keys(citation_map))
    candidate_path = stage.artifact_path(cwd, "paper.citation-repair.candidate.tex")
    candidate_path.write_text(candidate, encoding="utf-8")
    return candidate, {
        "candidate_path": str(candidate_path),
        "lane_type": lane_type,
        "fallback_used": fallback_used,
        "lane_notes": lane_notes,
        "unknown_citation_keys": unknown,
        "citation_replacements": citation_replacements,
    }


__all__ = ["build_repair_candidate"]
