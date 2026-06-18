from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .utils import _file_sha256

_V3_SUMMARY_KEYS = ("pass", "weak", "fail", "human_needed")


@dataclass(frozen=True)
class CitationSupportV3Summary:
    counts: dict[str, int]
    invalid_verdicts: list[str]


def summarize_v3_cases(cases: list[dict[str, Any]]) -> CitationSupportV3Summary:
    summary = {key: 0 for key in _V3_SUMMARY_KEYS}
    invalid_verdicts: list[str] = []
    for case in cases:
        verdict = str(case.get("verdict") or "human_needed")
        if verdict not in summary:
            invalid_verdicts.append(verdict)
            verdict = "human_needed"
        summary[verdict] += 1
    return CitationSupportV3Summary(counts=summary, invalid_verdicts=invalid_verdicts)


def v3_case_identity(cases: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return [(str(case.get("id")), str(case.get("key"))) for case in cases]


def v3_case_context_projection(case: dict[str, Any]) -> dict[str, str]:
    resolution = case.get("resolution") if isinstance(case.get("resolution"), dict) else {}
    comparable_target = case.get("target")
    if resolution.get("action") == "weaken_claim" and resolution.get("original_target"):
        comparable_target = resolution.get("original_target")
    return {
        "id": str(case.get("id") or ""),
        "key": str(case.get("key") or ""),
        "loc": normalize_v3_context_text(case.get("loc")),
        "paragraph": normalize_v3_context_text(case.get("paragraph")),
        "anchor": normalize_v3_context_text(case.get("anchor")),
        "target": normalize_v3_context_text(comparable_target),
    }


def v3_context_mismatch_indexes(current_cases: list[dict[str, Any]], review_cases: list[dict[str, Any]]) -> list[int]:
    current_context = [v3_case_context_projection(case) for case in current_cases]
    review_context = [v3_case_context_projection(case) for case in review_cases]
    return [
        index
        for index, (current_case, review_case) in enumerate(zip(current_context, review_context))
        if current_case != review_case
    ]


def normalize_v3_context_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def missing_v3_pass_evidence_count(cases: list[dict[str, Any]], run_root: Path) -> int:
    return sum(1 for case in cases if _pass_case_lacks_source_artifact(case, run_root))


def _pass_case_lacks_source_artifact(case: dict[str, Any], run_root: Path) -> bool:
    if str(case.get("verdict") or "human_needed") != "pass":
        return False
    evidence = case.get("evidence") if isinstance(case.get("evidence"), dict) else {}
    if str(evidence.get("status") or "missing") not in {"pdf", "html", "text"}:
        return True
    return not _evidence_text_ready(evidence.get("text"), run_root)


def _evidence_text_ready(value: Any, run_root: Path) -> bool:
    if not value:
        return False
    path = Path(str(value))
    if not path.is_absolute():
        path = run_root / path
    try:
        return path.exists() and path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def v3_failing_codes(
    *,
    reported_summary: dict[str, Any],
    summary: CitationSupportV3Summary,
    identity_mismatch: bool,
    context_mismatch_count: int,
    missing_source_artifacts: int,
) -> list[str]:
    failing_codes: list[str] = []
    if reported_summary != summary.counts:
        failing_codes.append("citation_support_summary_mismatch")
    if summary.invalid_verdicts:
        failing_codes.append("citation_support_invalid_status")
    if identity_mismatch:
        failing_codes.append("citation_support_case_coverage_mismatch")
    if context_mismatch_count:
        failing_codes.append("citation_support_case_context_mismatch")
    if summary.counts["weak"]:
        failing_codes.append("citation_support_weak")
    if summary.counts["fail"]:
        failing_codes.append("citation_support_unsupported")
    if summary.counts["human_needed"]:
        failing_codes.append("citation_support_manual_check")
    if missing_source_artifacts:
        failing_codes.append("citation_support_evidence_missing")
    return failing_codes


def build_v3_citation_support_result(
    *,
    path: Path,
    payload: dict[str, Any],
    cases: list[dict[str, Any]],
    current_cases: list[dict[str, Any]],
    review_context_count: int,
    current_context_count: int,
    context_mismatch_indexes: list[int],
    missing_source_artifacts: int,
    summary: CitationSupportV3Summary,
    reported_summary: dict[str, Any],
    failing_codes: list[str],
) -> dict[str, Any]:
    status = "fail" if failing_codes else "pass"
    return {
        "status": status,
        "path": str(path),
        "citation_review_sha256": _file_sha256(path),
        "summary": summary.counts,
        "canonical_summary": summary.counts,
        "reported_summary": reported_summary,
        "claims_checked": len(cases),
        "item_count": len(cases),
        "case_count": len(cases),
        "current_case_count": len(current_cases),
        "weakly_supported_count": summary.counts["weak"],
        "unsupported_count": summary.counts["fail"],
        "needs_manual_check_count": summary.counts["human_needed"],
        "evidence_missing_count": missing_source_artifacts,
        "context_mismatch_count": len(context_mismatch_indexes),
        "context_mismatch_indexes": context_mismatch_indexes,
        "review_case_context_count": review_context_count,
        "current_case_context_count": current_context_count,
        "evidence_mode": payload.get("mode"),
        "source_backed": True,
        "legacy_untrusted": False,
        "invalid_status_values": sorted(set(summary.invalid_verdicts)),
        "failing_codes": failing_codes,
    }


def _citation_support_check_v3(
    cwd: str | Path | None,
    state,
    path: Path,
    payload: dict[str, Any],
    *,
    quality_mode: str,
    case_builder: Callable[..., list[dict[str, Any]]],
) -> dict[str, Any]:
    del quality_mode
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
