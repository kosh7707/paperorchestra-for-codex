from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import read_json, write_json
from paperorchestra.core.models import SessionState, utc_now_iso
from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.visual.contact_sheet import write_contact_sheet_indexes
from paperorchestra.visual.page_render import render_pdf_pages

PAGE_LAYOUT_SCHEMA_VERSION = "page-layout-review/1"
VISUAL_FINDINGS_SCHEMA_VERSION = "page-visual-findings/1"
VISUAL_REPAIR_BRIEF_SCHEMA_VERSION = "visual-repair-brief/1"
VISUAL_REPAIR_CANDIDATE_SCHEMA_VERSION = "visual-repair-candidate/1"

SEMI_AUTO_VISUAL_CODES = {
    "visual_review_pending",
    "table_overflow",
    "figure_unreadable",
    "float_clump",
    "heading_orphan",
    "column_imbalance",
    "excessive_whitespace",
    "visual_style_inconsistent",
    "ai_generated_artifact",
    "garbled_or_blurry_text",
    "warped_geometry",
    "object_bleeding_or_unphysical_join",
    "overdecorated_ai_style",
    "inconsistent_light_shadow",
    "unsupported_decorative_icon",
    "publication_figure_overcrowded",
    "color_or_contrast_accessibility",
}
HUMAN_VISUAL_CODES = {
    "final_artwork_required",
    "semantic_visual_evidence_dispute",
    "human_aesthetic_preference",
}
FAIL_SEVERITIES = {"fail", "failed", "error", "critical", "block", "blocked"}
WARN_SEVERITIES = {"warn", "warning", "minor"}


def write_page_layout_review(
    cwd: str | Path | None,
    *,
    pdf_path: str | Path | None = None,
    output_path: str | Path | None = None,
    render_dir: str | Path | None = None,
    findings_json: str | Path | None = None,
    review_focus: str | None = None,
    require_ai_artifact_check: bool = False,
    require_publication_figure_check: bool = False,
) -> tuple[Path, dict[str, Any]]:
    state = _try_load_session(cwd)
    selected_pdf = Path(pdf_path or (state.artifacts.compiled_pdf if state else "") or "").expanduser()
    if not str(selected_pdf) or str(selected_pdf) == ".":
        raise ContractError("Need compiled PDF or --pdf before page visual audit.")
    selected_pdf = selected_pdf.resolve()
    if render_dir:
        selected_render_dir = Path(render_dir).resolve()
    elif state:
        selected_render_dir = artifact_path(cwd, "page-visual-render")
    else:
        selected_render_dir = Path(cwd or ".").resolve() / "page-visual-render"
    render_payload = render_pdf_pages(selected_pdf, selected_render_dir)
    pages = list(render_payload.get("pages") or [])
    contact_sheets = write_contact_sheet_indexes(pages, selected_render_dir) if pages else {}
    imported_findings = read_json(findings_json) if findings_json else None
    manuscript_path = (
        Path(state.artifacts.paper_full_tex).resolve()
        if state and state.artifacts.paper_full_tex
        else _infer_manuscript_path(selected_pdf)
    )
    payload = build_page_layout_review_payload(
        pdf_path=selected_pdf,
        manuscript_path=manuscript_path,
        rendered_pages=pages,
        contact_sheets=contact_sheets,
        imported_findings=imported_findings,
        imported_findings_path=findings_json,
        render_status={key: value for key, value in render_payload.items() if key != "pages"},
        review_focus=review_focus,
        require_ai_artifact_check=require_ai_artifact_check,
        require_publication_figure_check=require_publication_figure_check,
    )
    if output_path:
        path = Path(output_path).resolve()
    elif state:
        path = artifact_path(cwd, "page-layout-review.json")
    else:
        path = Path(cwd or ".").resolve() / "page-layout-review.json"
    write_json(path, payload)
    if state:
        state.artifacts.latest_page_layout_review_json = str(path)
        save_session(cwd, state)
    return path, payload


def _try_load_session(cwd: str | Path | None) -> SessionState | None:
    try:
        return load_session(cwd)
    except FileNotFoundError:
        return None


def _infer_manuscript_path(pdf_path: Path) -> Path | None:
    sibling = pdf_path.with_suffix(".tex")
    return sibling.resolve() if sibling.exists() else None


def build_page_layout_review_payload(
    *,
    pdf_path: str | Path,
    manuscript_path: str | Path | None,
    rendered_pages: list[dict[str, Any]],
    contact_sheets: dict[str, Any],
    imported_findings: dict[str, Any] | None,
    render_status: dict[str, Any],
    imported_findings_path: str | Path | None = None,
    review_focus: str | None = None,
    require_ai_artifact_check: bool = False,
    require_publication_figure_check: bool = False,
) -> dict[str, Any]:
    imported_findings_valid = _valid_imported_findings(imported_findings)
    required_checks = _required_visual_checks(
        require_ai_artifact_check=require_ai_artifact_check,
        require_publication_figure_check=require_publication_figure_check,
    )
    missing_required_checks = _missing_required_visual_checks(required_checks, imported_findings if imported_findings_valid else None)
    page_findings, document_findings = _normalized_findings(imported_findings if imported_findings_valid else None)
    failing_codes, warning_codes = _finding_codes(page_findings + document_findings)
    if missing_required_checks:
        failing_codes.append("required_visual_check_missing")
    repair_candidates = _repair_candidates(page_findings, document_findings)
    requires_visual_reviewer = not imported_findings_valid
    if requires_visual_reviewer:
        warning_codes.append("visual_review_pending")
        repair_candidates.append(_pending_visual_review_candidate(rendered_pages, contact_sheets))
    if missing_required_checks:
        repair_candidates.append(_missing_required_visual_checks_candidate(missing_required_checks))
    if str(render_status.get("status") or "").lower() not in {"pass", "ok", "success"}:
        render_code = "visual_render_unavailable" if render_status.get("status") == "unavailable" else "visual_render_failed"
        failing_codes.append(render_code)
        repair_candidates.append(_render_repair_candidate(render_code, render_status))
    failing_codes = _unique_sorted(failing_codes)
    warning_codes = _unique_sorted(warning_codes)
    return {
        "schema_version": PAGE_LAYOUT_SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "status": _review_status(failing_codes, warning_codes),
        "pdf_path": str(Path(pdf_path).resolve()),
        "compiled_pdf_sha256": _file_sha256(pdf_path),
        "manuscript_path": str(Path(manuscript_path).resolve()) if manuscript_path else None,
        "manuscript_sha256": _file_sha256(manuscript_path),
        "render_status": render_status,
        "rendered_pages": rendered_pages,
        "contact_sheets": contact_sheets,
        "requires_visual_reviewer": requires_visual_reviewer,
        "review_focus": review_focus,
        "required_visual_checks": required_checks,
        "completed_visual_checks": _completed_visual_checks(imported_findings if imported_findings_valid else None),
        "missing_required_visual_checks": missing_required_checks,
        "imported_findings_path": str(Path(imported_findings_path).resolve()) if imported_findings_path else None,
        "imported_findings_schema_version": imported_findings.get("schema_version") if isinstance(imported_findings, dict) else None,
        "imported_findings_valid": imported_findings_valid,
        "reviewer": imported_findings.get("reviewer") if isinstance(imported_findings, dict) else None,
        "page_findings": page_findings,
        "document_findings": document_findings,
        "failing_codes": failing_codes,
        "warning_codes": warning_codes,
        "repair_candidates": repair_candidates,
    }


def build_visual_repair_brief_payload(review_payload: dict[str, Any], *, source_review_path: str | Path | None) -> dict[str, Any]:
    actions = [_brief_action(candidate, index=index) for index, candidate in enumerate(review_payload.get("repair_candidates") or [], start=1)]
    return {
        "schema_version": VISUAL_REPAIR_BRIEF_SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "source_review": str(source_review_path) if source_review_path else review_payload.get("source_review"),
        "source_review_sha256": _file_sha256(source_review_path),
        "manuscript_sha256": review_payload.get("manuscript_sha256"),
        "status": "human_needed" if any(action["automation"] == "human_needed" for action in actions) else "ready_for_repair",
        "action_count": len(actions),
        "actions": actions,
    }


def build_visual_repair_candidate_payload(brief_payload: dict[str, Any], *, source_brief_path: str | Path | None) -> dict[str, Any]:
    source_actions = [item for item in brief_payload.get("actions") or [] if isinstance(item, dict)]
    candidate_actions = [_candidate_action(item, index=index) for index, item in enumerate(source_actions, start=1)]
    return {
        "schema_version": VISUAL_REPAIR_CANDIDATE_SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "source_brief": str(source_brief_path) if source_brief_path else None,
        "source_brief_sha256": _file_sha256(source_brief_path),
        "source_review": brief_payload.get("source_review"),
        "manuscript_sha256": brief_payload.get("manuscript_sha256"),
        "status": "candidate_ready",
        "candidate_count": len(candidate_actions),
        "candidate_actions": candidate_actions,
        "verification_loop": [
            "Apply only the bounded TeX/figure/table change described by the selected candidate action.",
            "Recompile the manuscript.",
            "Rerun paperorchestra visual-audit against the new PDF and imported visual findings.",
            "Accept only if the original finding disappears without introducing stronger claims or caption drift.",
        ],
    }


def write_visual_repair_brief(
    cwd: str | Path | None,
    *,
    review_path: str | Path | None = None,
    output_path: str | Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    state = load_session(cwd)
    selected_review = Path(review_path or state.artifacts.latest_page_layout_review_json or "").expanduser()
    if not str(selected_review) or str(selected_review) == ".":
        raise ContractError("Need page-layout-review.json before visual repair brief.")
    selected_review = selected_review.resolve()
    review_payload = read_json(selected_review)
    payload = build_visual_repair_brief_payload(review_payload, source_review_path=selected_review)
    path = Path(output_path).resolve() if output_path else artifact_path(cwd, "visual_repair_brief.json")
    write_json(path, payload)
    state.artifacts.latest_visual_repair_brief_json = str(path)
    save_session(cwd, state)
    return path, payload


def write_visual_repair_candidate(
    cwd: str | Path | None,
    *,
    brief_path: str | Path | None = None,
    output_path: str | Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    state = load_session(cwd)
    selected_brief = Path(brief_path or state.artifacts.latest_visual_repair_brief_json or "").expanduser()
    if not str(selected_brief) or str(selected_brief) == ".":
        raise ContractError("Need visual_repair_brief.json before visual repair candidate.")
    selected_brief = selected_brief.resolve()
    brief_payload = read_json(selected_brief)
    payload = build_visual_repair_candidate_payload(brief_payload, source_brief_path=selected_brief)
    path = Path(output_path).resolve() if output_path else artifact_path(cwd, "visual_repair_candidate.json")
    write_json(path, payload)
    state.artifacts.latest_visual_repair_candidate_json = str(path)
    save_session(cwd, state)
    return path, payload


def _required_visual_checks(*, require_ai_artifact_check: bool, require_publication_figure_check: bool) -> list[str]:
    checks: list[str] = []
    if require_ai_artifact_check:
        checks.append("ai_artifact_check")
    if require_publication_figure_check:
        checks.append("publication_figure_check")
    return checks


def _completed_visual_checks(imported_findings: dict[str, Any] | None) -> list[str]:
    if not isinstance(imported_findings, dict):
        return []
    raw = imported_findings.get("checks_completed") or imported_findings.get("completed_checks") or []
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def _missing_required_visual_checks(required_checks: list[str], imported_findings: dict[str, Any] | None) -> list[str]:
    completed = set(_completed_visual_checks(imported_findings))
    return [check for check in required_checks if check not in completed]


def _valid_imported_findings(imported_findings: dict[str, Any] | None) -> bool:
    if not isinstance(imported_findings, dict):
        return False
    if imported_findings.get("schema_version") != VISUAL_FINDINGS_SCHEMA_VERSION:
        return False
    if not str(imported_findings.get("reviewer") or "").strip():
        return False
    page = imported_findings.get("page_findings")
    document = imported_findings.get("document_findings")
    if page is None and document is None:
        return False
    if page is not None and not isinstance(page, list):
        return False
    if document is not None and not isinstance(document, list):
        return False
    return all(_valid_finding_item(item, require_page=True) for item in page or []) and all(
        _valid_finding_item(item, require_page=False) for item in document or []
    )


def _valid_finding_item(item: Any, *, require_page: bool) -> bool:
    if not isinstance(item, dict):
        return False
    if require_page and not isinstance(item.get("page"), int):
        return False
    required_text_fields = ("code", "severity", "target", "detail")
    return all(isinstance(item.get(field), str) and item.get(field).strip() for field in required_text_fields)


def _normalized_findings(imported_findings: dict[str, Any] | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(imported_findings, dict):
        return [], []
    return (
        [_normalized_finding(item, scope="page") for item in imported_findings.get("page_findings") or [] if isinstance(item, dict)],
        [_normalized_finding(item, scope="document") for item in imported_findings.get("document_findings") or [] if isinstance(item, dict)],
    )


def _normalized_finding(item: dict[str, Any], *, scope: str) -> dict[str, Any]:
    return {
        "scope": scope,
        "page": item.get("page") if isinstance(item.get("page"), int) else None,
        "code": str(item.get("code") or "visual_issue").strip() or "visual_issue",
        "severity": str(item.get("severity") or "warn").strip().lower() or "warn",
        "target": str(item.get("target") or scope).strip() or scope,
        "detail": str(item.get("detail") or item.get("message") or "").strip(),
        "suggested_fix": str(item.get("suggested_fix") or item.get("suggestion") or "").strip(),
    }


def _finding_codes(findings: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    failing: list[str] = []
    warning: list[str] = []
    for finding in findings:
        severity = str(finding.get("severity") or "").lower()
        code = str(finding.get("code") or "").strip()
        if not code:
            continue
        if severity in FAIL_SEVERITIES:
            failing.append(code)
        elif severity in WARN_SEVERITIES or severity:
            warning.append(code)
    return failing, warning


def _repair_candidates(page_findings: list[dict[str, Any]], document_findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_repair_candidate(finding) for finding in [*page_findings, *document_findings]]


def _repair_candidate(finding: dict[str, Any]) -> dict[str, Any]:
    code = str(finding.get("code") or "visual_issue")
    automation = _automation_for_code(code)
    return {
        "code": code,
        "source_finding_code": code,
        "automation": automation,
        "scope": finding.get("scope"),
        "page": finding.get("page"),
        "target": finding.get("target"),
        "detail": finding.get("detail"),
        "suggested_fix": finding.get("suggested_fix"),
        "proposed_owner": "human" if automation == "human_needed" else "paperorchestra",
        "candidate_instruction": _candidate_instruction(finding, automation=automation),
    }


def _pending_visual_review_candidate(rendered_pages: list[dict[str, Any]], contact_sheets: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": "visual_review_pending",
        "source_finding_code": "visual_review_pending",
        "automation": "semi_auto",
        "scope": "document",
        "page": None,
        "target": "rendered PDF pages",
        "detail": "Rendered page images exist, but no imported page-visual-findings review has been provided yet.",
        "suggested_fix": "Run a vision reviewer or $visual-verdict over the contact sheet, including AI-artifact and publication-figure checks, then rerun visual-audit with --findings-json.",
        "proposed_owner": "paperorchestra",
        "candidate_instruction": (
            "Use the rendered page images/contact sheet to obtain visual findings; do not mark the PDF visually accepted from TeX-only evidence."
        ),
        "page_count": len(rendered_pages),
        "contact_sheets": contact_sheets,
    }


def _missing_required_visual_checks_candidate(missing_checks: list[str]) -> dict[str, Any]:
    return {
        "code": "required_visual_check_missing",
        "source_finding_code": "required_visual_check_missing",
        "automation": "semi_auto",
        "scope": "document",
        "page": None,
        "target": "required PaperOrchestra figure visual checks",
        "detail": "Imported findings did not declare completed required visual checks: " + ", ".join(missing_checks),
        "suggested_fix": "Run a vision reviewer or $visual-verdict with category_hint=paper-figure, record checks_completed, then rerun visual-audit.",
        "proposed_owner": "paperorchestra",
        "candidate_instruction": "Do not accept generated figure artwork until AI-artifact and publication-figure checks are explicitly completed in findings JSON.",
    }


def _render_repair_candidate(code: str, render_status: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": code,
        "source_finding_code": code,
        "automation": "automatic",
        "scope": "document",
        "page": None,
        "target": "rendered PDF page evidence",
        "detail": str(render_status.get("reason") or render_status.get("status") or "render failed"),
        "suggested_fix": "Regenerate a clean compiled PDF and rerun page visual audit; do not accept visual/layout claims without rendered page evidence.",
        "proposed_owner": "paperorchestra",
        "candidate_instruction": "Fix render preconditions or re-render the current compiled PDF before any visual acceptance.",
    }


def _automation_for_code(code: str) -> str:
    if code in HUMAN_VISUAL_CODES:
        return "human_needed"
    if code in SEMI_AUTO_VISUAL_CODES:
        return "semi_auto"
    return "semi_auto"


def _candidate_instruction(finding: dict[str, Any], *, automation: str) -> str:
    target = finding.get("target") or "visual artifact"
    fix = finding.get("suggested_fix") or "prepare a minimal visual/layout repair"
    if automation == "human_needed":
        return f"Prepare a bounded human handoff for {target}: {fix}"
    return f"Prepare a PaperOrchestra repair candidate for {target}: {fix}"


def _brief_action(candidate: dict[str, Any], *, index: int) -> dict[str, Any]:
    code = str(candidate.get("code") or "visual_issue")
    automation = str(candidate.get("automation") or _automation_for_code(code))
    return {
        "id": f"visual-repair:{index}",
        "code": code,
        "source_finding_code": candidate.get("source_finding_code") or code,
        "automation": automation,
        "target": candidate.get("target"),
        "page": candidate.get("page"),
        "detail": candidate.get("detail"),
        "suggested_fix": candidate.get("suggested_fix"),
        "proposed_owner": "human" if automation == "human_needed" else "paperorchestra",
        "candidate_instruction": candidate.get("candidate_instruction") or _candidate_instruction(candidate, automation=automation),
        "acceptance_checks": [
            "The repaired page still supports the same manuscript claim; no stronger claim is introduced.",
            "The figure/table remains near the intended rhetorical location or has a documented float reason.",
            "The caption remains accurate, self-contained, and aligned with the visual after repair.",
            "No AI-generated-artifact tells remain: garbled text, warped geometry, impossible joins, inconsistent lighting/shadows, overdecorated stock-art sheen, or unsupported decorative icons.",
            "One-column/two-column layout choice remains readable and does not overflow page or column bounds.",
            "Recompile and rerun page visual audit after the candidate repair.",
        ],
    }


def _candidate_action(action: dict[str, Any], *, index: int) -> dict[str, Any]:
    code = str(action.get("code") or "visual_issue")
    target = action.get("target") or "visual artifact"
    return {
        "id": f"visual-candidate:{index}",
        "source_action_id": action.get("id"),
        "code": code,
        "target": target,
        "page": action.get("page"),
        "proposed_owner": action.get("proposed_owner") or "paperorchestra",
        "patch_strategy": _patch_strategy_for_code(code),
        "draft_instruction": (
            f"Repair {target} for visual finding {code}. "
            f"Use the suggested fix if safe: {action.get('suggested_fix') or action.get('candidate_instruction') or 'make the smallest layout-preserving change'}"
        ),
        "claim_location_caption_guard": [
            "Do not strengthen the affected claim.",
            "Keep the figure/table near the paragraph that interprets it unless the venue float rules force movement.",
            "Update the caption only to preserve accuracy after the visual change.",
        ],
        "acceptance_checks": action.get("acceptance_checks") or [],
    }


def _patch_strategy_for_code(code: str) -> str:
    return {
        "visual_render_unavailable": "restore_render_backend_or_regenerate_pdf",
        "visual_render_failed": "regenerate_clean_pdf_and_rerender",
        "table_overflow": "shrink_or_reflow_table_without_changing_values",
        "figure_unreadable": "increase_effective_figure_width_or_simplify_labels",
        "float_clump": "redistribute_floats_near_first_reference",
        "heading_orphan": "move_float_or_text_to_keep_heading_with_content",
        "column_imbalance": "rebalance_float_width_or_placement",
        "excessive_whitespace": "reduce_float_gap_or_move_float",
        "visual_style_inconsistent": "normalize_visual_palette_typography_and_line_weight",
        "visual_review_pending": "obtain_visual_findings_from_contact_sheet",
    }.get(code, "make_smallest_visual_layout_repair")


def _review_status(failing_codes: list[str], warning_codes: list[str]) -> str:
    if failing_codes:
        return "fail"
    if warning_codes:
        return "warn"
    return "pass"


def _unique_sorted(values: list[str]) -> list[str]:
    return sorted(dict.fromkeys(value for value in values if value))


def _file_sha256(path: str | Path | None) -> str | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return None
    return hashlib.sha256(candidate.read_bytes()).hexdigest()
