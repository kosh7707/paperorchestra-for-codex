from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from paperorchestra.core.io import write_json
from paperorchestra.core.models import utc_now_iso
from paperorchestra.core.session import artifact_path, load_session, runtime_root, save_session
from paperorchestra.manuscript.validator import ValidationIssue, validate_manuscript
from paperorchestra.reviews.fidelity import run_fidelity_audit
from paperorchestra.runtime.compile_env import inspect_compile_environment


def _issue_messages(issues: list[ValidationIssue]) -> list[str]:
    return [issue.message for issue in issues]


def _blocking_issues(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    return [issue for issue in issues if issue.severity == "error"]


def collect_paper_contract_issues(
    latex: str,
    *,
    citation_map: dict[str, Any],
    figures_dir: str | None,
    plot_manifest: dict[str, Any] | None = None,
    plot_assets_index: dict[str, Any] | None = None,
    experimental_log_text: str | None = None,
    expected_section_titles: list[str] | None = None,
    narrative_plan: dict[str, Any] | None = None,
    claim_map: dict[str, Any] | None = None,
    citation_placement_plan: dict[str, Any] | None = None,
) -> list[ValidationIssue]:
    return validate_manuscript(
        latex,
        citation_map=citation_map,
        figures_dir=figures_dir,
        plot_manifest=plot_manifest,
        plot_assets_index=plot_assets_index,
        experimental_log_text=experimental_log_text,
        expected_section_titles=expected_section_titles,
        narrative_plan=narrative_plan,
        claim_map=claim_map,
        citation_placement_plan=citation_placement_plan,
    )


def _validation_report_payload(
    stage: str,
    issues: list[ValidationIssue],
    *,
    manuscript_path: str | None = None,
    manuscript_text: str | None = None,
) -> dict[str, Any]:
    blocking = _blocking_issues(issues)
    warnings = [issue for issue in issues if issue.severity != "error"]
    payload = {
        "stage": stage,
        "ok": not blocking,
        "blocking_issue_count": len(blocking),
        "warning_count": len(warnings),
        "issues": [issue.to_dict() for issue in issues],
        "generated_at": utc_now_iso(),
    }
    if manuscript_path:
        payload["manuscript_path"] = manuscript_path
    if manuscript_text is not None:
        payload["manuscript_sha256"] = hashlib.sha256(manuscript_text.encode("utf-8")).hexdigest()
    elif manuscript_path and Path(manuscript_path).exists():
        payload["manuscript_sha256"] = hashlib.sha256(Path(manuscript_path).read_bytes()).hexdigest()
    return payload


def _record_validation_report(
    cwd: str | Path | None,
    *,
    stage: str,
    issues: list[ValidationIssue],
    name: str,
    manuscript_path: str | None = None,
    manuscript_text: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    path = artifact_path(cwd, name)
    payload = _validation_report_payload(
        stage,
        issues,
        manuscript_path=manuscript_path,
        manuscript_text=manuscript_text,
    )
    write_json(path, payload)
    state = load_session(cwd)
    state.artifacts.latest_validation_json = str(path)
    save_session(cwd, state)
    return path, payload


def record_compile_environment_report(cwd: str | Path | None, *, name: str = "compile-environment.json") -> tuple[Path, dict[str, Any]]:
    report = inspect_compile_environment(cwd)
    payload = report.to_dict()
    try:
        path = artifact_path(cwd, name)
        write_json(path, payload)
        state = load_session(cwd)
        state.artifacts.latest_compile_env_json = str(path)
        save_session(cwd, state)
    except FileNotFoundError:
        path = runtime_root(cwd) / "preflight" / name
        write_json(path, payload)
    return path, payload


def record_fidelity_report(cwd: str | Path | None, *, name: str = "fidelity.audit.json") -> tuple[Path, dict[str, Any]]:
    payload = run_fidelity_audit(cwd)
    path = artifact_path(cwd, name)
    write_json(path, payload)
    state = load_session(cwd)
    state.artifacts.latest_fidelity_json = str(path)
    save_session(cwd, state)
    return path, payload


def validate_paper_contract(
    latex: str,
    *,
    citation_map: dict[str, Any],
    figures_dir: str | None,
    plot_manifest: dict[str, Any] | None = None,
    plot_assets_index: dict[str, Any] | None = None,
    experimental_log_text: str | None = None,
    expected_section_titles: list[str] | None = None,
) -> list[str]:
    issues = collect_paper_contract_issues(
        latex,
        citation_map=citation_map,
        figures_dir=figures_dir,
        plot_manifest=plot_manifest,
        plot_assets_index=plot_assets_index,
        experimental_log_text=experimental_log_text,
        expected_section_titles=expected_section_titles,
    )
    return _issue_messages(issues)
