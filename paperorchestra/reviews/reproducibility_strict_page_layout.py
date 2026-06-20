from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.reviews.reproducibility_artifacts import _file_sha256, _read_json_if_exists

HUMAN_VISUAL_CODES = {
    "final_artwork_required",
    "semantic_visual_evidence_dispute",
    "human_aesthetic_preference",
}
PAGE_LAYOUT_ACTIONABLE_WARNING_CODES = {
    "visual_review_pending",
    "table_overflow",
    "figure_unreadable",
    "float_clump",
    "heading_orphan",
    "column_imbalance",
    "excessive_whitespace",
    "visual_style_inconsistent",
    "visual_render_unavailable",
    "visual_render_failed",
}


def _strict_page_layout_review_issues(state: Any, session_artifact_dir: Path | None) -> list[dict[str, Any]]:
    expected_manuscript_sha = _file_sha256(state.artifacts.paper_full_tex)
    expected_pdf_sha = _file_sha256(getattr(state.artifacts, "compiled_pdf", None))
    candidates: list[Path] = []
    latest_page_review = getattr(state.artifacts, "latest_page_layout_review_json", None)
    if latest_page_review:
        candidates.append(Path(latest_page_review))
    if session_artifact_dir is not None:
        candidates.append(session_artifact_dir / "page-layout-review.json")

    issues: list[dict[str, Any]] = []
    found_review = False
    for path in _existing_unique_paths(candidates):
        payload = _read_json_if_exists(path)
        if not payload:
            continue
        found_review = True
        if _page_layout_review_is_stale(payload, expected_manuscript_sha=expected_manuscript_sha, expected_pdf_sha=expected_pdf_sha):
            issues.append(
                {
                    "source": str(path),
                    "stage": "page_layout",
                    "kind": "page_layout_review_stale",
                    "code": "page_layout_review_stale",
                    "message": "Page-layout visual review is missing or stale for the current manuscript/PDF.",
                    "severity": "error",
                }
            )
            continue
        issues.extend(_strict_page_layout_payload_issues(path, payload))
    if state.artifacts.paper_full_tex and getattr(state.artifacts, "compiled_pdf", None) and expected_manuscript_sha and not found_review:
        issues.append(
            {
                "source": None,
                "stage": "page_layout",
                "kind": "page_layout_review_missing",
                "code": "page_layout_review_missing",
                "message": "Strict content gates require a current rendered-page visual review for the compiled manuscript.",
                "severity": "error",
            }
        )
    return issues


def _page_layout_review_is_stale(
    payload: dict[str, Any],
    *,
    expected_manuscript_sha: str | None,
    expected_pdf_sha: str | None,
) -> bool:
    if expected_manuscript_sha and payload.get("manuscript_sha256") != expected_manuscript_sha:
        return True
    if expected_pdf_sha and payload.get("compiled_pdf_sha256") != expected_pdf_sha:
        return True
    return False


def _existing_unique_paths(candidates: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen or not path.exists():
            continue
        seen.add(resolved)
        result.append(path)
    return result


def _strict_page_layout_payload_issues(path: Path, payload: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    render_status = payload.get("render_status") if isinstance(payload.get("render_status"), dict) else {}
    if str(render_status.get("status") or "").lower() in {"fail", "failed", "unavailable", "error"}:
        issues.append(_page_layout_issue(path, _render_issue_code(render_status), severity="error", kind="page_layout_render_blocker"))
    for code in payload.get("failing_codes") or []:
        issues.append(_page_layout_issue(path, str(code), severity="error", kind="page_layout_failure"))
    for code in payload.get("warning_codes") or []:
        if code in PAGE_LAYOUT_ACTIONABLE_WARNING_CODES:
            issues.append(_page_layout_issue(path, str(code), severity="warning", kind="page_layout_warning"))
    return _dedupe_issues(issues)


def _render_issue_code(render_status: dict[str, Any]) -> str:
    return "visual_render_unavailable" if render_status.get("status") == "unavailable" else "visual_render_failed"


def _page_layout_issue(path: Path, source_code: str, *, severity: str, kind: str) -> dict[str, Any]:
    if source_code in HUMAN_VISUAL_CODES:
        return {
            "source": str(path),
            "stage": "page_layout",
            "kind": "page_layout_human",
            "code": "visual_final_artwork_handoff",
            "source_finding_code": source_code,
            "message": f"Rendered-page visual audit requires human visual ownership for {source_code}.",
            "severity": severity,
        }
    action_code = _action_code_for_source(source_code)
    return {
        "source": str(path),
        "stage": "page_layout",
        "kind": kind,
        "code": action_code,
        "source_finding_code": source_code,
        "message": f"Rendered-page visual audit reported {source_code}; repair or regenerate visual evidence before handoff.",
        "severity": severity,
    }


def _action_code_for_source(source_code: str) -> str:
    if source_code == "visual_render_unavailable":
        return "page_layout_render_unavailable"
    if source_code == "visual_render_failed":
        return "page_layout_render_failed"
    return "visual_layout_repair_brief_needed"


def _dedupe_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None]] = set()
    for issue in issues:
        key = (str(issue.get("code")), issue.get("source_finding_code"))
        if key in seen:
            continue
        seen.add(key)
        result.append(issue)
    return result
