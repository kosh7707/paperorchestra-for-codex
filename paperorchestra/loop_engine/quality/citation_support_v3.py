from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .citation_support_v3_cases import (
    CitationSupportV3Summary,
    build_v3_citation_support_result,
    missing_v3_pass_evidence_count,
    normalize_v3_context_text,
    summarize_v3_cases,
    v3_case_context_projection,
    v3_case_identity,
    v3_context_mismatch_indexes,
    v3_failing_codes,
)


def _citation_support_check_v3(
    cwd: str | Path | None,
    state,
    path: Path,
    payload: dict[str, Any],
    *,
    quality_mode: str,
    case_builder: Callable[..., list[dict[str, Any]]],
) -> dict[str, Any]:
    del quality_mode, state
    cases = [case for case in payload.get("cases", []) if isinstance(case, dict)] if isinstance(payload.get("cases"), list) else []
    summary = summarize_v3_cases(cases)
    reported_summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    try:
        current_cases = case_builder(cwd, resolve_evidence=False)
    except Exception:
        current_cases = []
    current_identity = v3_case_identity(current_cases)
    review_identity = v3_case_identity(cases)
    identity_mismatch = current_identity != review_identity
    context_mismatch_indexes = [] if identity_mismatch else v3_context_mismatch_indexes(current_cases, cases)
    current_context_count = len([v3_case_context_projection(case) for case in current_cases])
    review_context_count = len([v3_case_context_projection(case) for case in cases])
    missing_source_artifacts = missing_v3_pass_evidence_count(cases, path.parent.parent)
    failing_codes = v3_failing_codes(
        reported_summary=reported_summary,
        summary=summary,
        identity_mismatch=identity_mismatch,
        context_mismatch_count=len(context_mismatch_indexes),
        missing_source_artifacts=missing_source_artifacts,
    )
    return build_v3_citation_support_result(
        path=path,
        payload=payload,
        cases=cases,
        current_cases=current_cases,
        review_context_count=review_context_count,
        current_context_count=current_context_count,
        context_mismatch_indexes=context_mismatch_indexes,
        missing_source_artifacts=missing_source_artifacts,
        summary=summary,
        reported_summary=reported_summary,
        failing_codes=failing_codes,
    )


__all__ = [
    "CitationSupportV3Summary",
    "_citation_support_check_v3",
    "build_v3_citation_support_result",
    "missing_v3_pass_evidence_count",
    "normalize_v3_context_text",
    "summarize_v3_cases",
    "v3_case_context_projection",
    "v3_case_identity",
    "v3_context_mismatch_indexes",
    "v3_failing_codes",
]
