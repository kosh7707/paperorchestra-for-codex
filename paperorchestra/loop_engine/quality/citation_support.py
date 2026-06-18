from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.reviews.source_support import build_source_backed_citation_cases
from .utils import _file_sha256, _read_json_if_exists
from paperorchestra.core.session import artifact_path
from paperorchestra.loop_engine.quality.citation_support_legacy import _legacy_citation_support_check


def _citation_support_path(cwd: str | Path | None, state) -> Path:
    if state.artifacts.paper_full_tex:
        return Path(state.artifacts.paper_full_tex).resolve().parent / "citation_support_review.json"
    return artifact_path(cwd, "citation_support_review.json")


def _citation_support_check(cwd: str | Path | None, state, *, quality_mode: str = "ralph") -> dict[str, Any]:
    path = _citation_support_path(cwd, state)
    payload = _read_json_if_exists(path)
    if not isinstance(payload, dict):
        return {"status": "fail", "path": str(path), "failing_codes": ["citation_support_review_missing"], "summary": None}
    if payload.get("schema") == "citation-support-review/3":
        return _citation_support_check_v3(cwd, state, path, payload, quality_mode=quality_mode)
    return _legacy_citation_support_check(cwd, state, path, payload, quality_mode=quality_mode)


def _citation_support_check_v3(
    cwd: str | Path | None,
    state,
    path: Path,
    payload: dict[str, Any],
    *,
    quality_mode: str,
) -> dict[str, Any]:
    raw_cases = payload.get("cases") if isinstance(payload.get("cases"), list) else []
    cases = [case for case in raw_cases if isinstance(case, dict)]
    summary = {"pass": 0, "weak": 0, "fail": 0, "human_needed": 0}
    invalid_verdicts: list[str] = []
    for case in cases:
        verdict = str(case.get("verdict") or "human_needed")
        if verdict not in summary:
            invalid_verdicts.append(verdict)
            verdict = "human_needed"
        summary[verdict] += 1
    reported_summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    failing_codes: list[str] = []
    if reported_summary != summary:
        failing_codes.append("citation_support_summary_mismatch")
    if invalid_verdicts:
        failing_codes.append("citation_support_invalid_status")
    try:
        current_cases = build_source_backed_citation_cases(cwd, resolve_evidence=False)
    except Exception:
        current_cases = []
    current_identity = [(str(case.get("id")), str(case.get("key"))) for case in current_cases]
    review_identity = [(str(case.get("id")), str(case.get("key"))) for case in cases]
    if current_identity != review_identity:
        failing_codes.append("citation_support_case_coverage_mismatch")
    current_context = [_v3_case_context_projection(case) for case in current_cases]
    review_context = [_v3_case_context_projection(case) for case in cases]
    context_mismatch_indexes: list[int] = []
    if current_identity == review_identity:
        context_mismatch_indexes = [
            index
            for index, (current_case, review_case) in enumerate(zip(current_context, review_context))
            if current_case != review_case
        ]
        if context_mismatch_indexes:
            failing_codes.append("citation_support_case_context_mismatch")

    missing_source_artifacts = 0
    run_root = path.parent.parent
    for case in cases:
        evidence = case.get("evidence") if isinstance(case.get("evidence"), dict) else {}
        verdict = str(case.get("verdict") or "human_needed")
        status = str(evidence.get("status") or "missing")
        if verdict == "pass":
            text_value = evidence.get("text")
            text_path = run_root / str(text_value) if isinstance(text_value, str) and not Path(text_value).is_absolute() else Path(str(text_value)) if text_value else None
            text_ready = False
            try:
                text_ready = bool(text_path and text_path.exists() and text_path.is_file() and text_path.stat().st_size > 0)
            except OSError:
                text_ready = False
            if status not in {"pdf", "html", "text"} or not text_ready:
                missing_source_artifacts += 1
    if summary["weak"]:
        failing_codes.append("citation_support_weak")
    if summary["fail"]:
        failing_codes.append("citation_support_unsupported")
    if summary["human_needed"]:
        failing_codes.append("citation_support_manual_check")
    if missing_source_artifacts:
        failing_codes.append("citation_support_evidence_missing")
    status = "fail" if failing_codes else "pass"
    return {
        "status": status,
        "path": str(path),
        "citation_review_sha256": _file_sha256(path),
        "summary": summary,
        "canonical_summary": summary,
        "reported_summary": reported_summary,
        "claims_checked": len(cases),
        "item_count": len(cases),
        "case_count": len(cases),
        "current_case_count": len(current_cases),
        "weakly_supported_count": summary["weak"],
        "unsupported_count": summary["fail"],
        "needs_manual_check_count": summary["human_needed"],
        "evidence_missing_count": missing_source_artifacts,
        "context_mismatch_count": len(context_mismatch_indexes),
        "context_mismatch_indexes": context_mismatch_indexes,
        "review_case_context_count": len(review_context),
        "current_case_context_count": len(current_context),
        "evidence_mode": payload.get("mode"),
        "source_backed": True,
        "legacy_untrusted": False,
        "invalid_status_values": sorted(set(invalid_verdicts)),
        "failing_codes": failing_codes,
    }


def _v3_case_context_projection(case: dict[str, Any]) -> dict[str, str]:
    resolution = case.get("resolution") if isinstance(case.get("resolution"), dict) else {}
    comparable_target = case.get("target")
    if resolution.get("action") == "weaken_claim" and resolution.get("original_target"):
        comparable_target = resolution.get("original_target")
    return {
        "id": str(case.get("id") or ""),
        "key": str(case.get("key") or ""),
        "loc": _normalize_v3_context_text(case.get("loc")),
        "paragraph": _normalize_v3_context_text(case.get("paragraph")),
        "anchor": _normalize_v3_context_text(case.get("anchor")),
        "target": _normalize_v3_context_text(comparable_target),
    }


def _normalize_v3_context_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def ensure_final_citation_review_bound_to_quality_eval(quality_eval_path: str | Path, final_review_path: str | Path) -> dict[str, Any]:
    """Validate that a surfaced final citation review is the gate-of-record artifact."""
    quality_eval = _read_json_if_exists(quality_eval_path)
    source_artifacts = quality_eval.get("source_artifacts") if isinstance(quality_eval, dict) else {}
    expected_sha = source_artifacts.get("citation_review_sha256") if isinstance(source_artifacts, dict) else None
    actual_sha = _file_sha256(final_review_path)
    if expected_sha and str(expected_sha).startswith("sha256:"):
        expected_sha = str(expected_sha).split("sha256:", 1)[1]
    if actual_sha and str(actual_sha).startswith("sha256:"):
        actual_sha = str(actual_sha).split("sha256:", 1)[1]
    if not expected_sha:
        raise ValueError("quality-eval source_artifacts.citation_review_sha256 is missing")
    if not actual_sha:
        raise ValueError(f"final citation review does not exist or is unreadable: {final_review_path}")
    if str(expected_sha) != str(actual_sha):
        raise ValueError(
            "final citation review is not bound to gate-of-record citation review "
            f"(expected sha256:{expected_sha}, actual sha256:{actual_sha})"
        )
    return {
        "status": "pass",
        "quality_eval_path": str(quality_eval_path),
        "final_review_path": str(final_review_path),
        "citation_review_sha256": str(actual_sha),
    }
