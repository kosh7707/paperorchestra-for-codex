from __future__ import annotations

from dataclasses import dataclass
import sys
from pathlib import Path
from typing import Any

from paperorchestra.core.io import write_text
from paperorchestra.core.session import artifact_path
from paperorchestra.engine.completion_trace import _file_sha256
from paperorchestra.engine.reports import _blocking_issues, _record_validation_report, collect_paper_contract_issues
from paperorchestra.manuscript.validation_types import ValidationIssue


@dataclass(frozen=True)
class RefinementContractCheckResult:
    latex: str
    validation_issues: list[ValidationIssue]
    blocking_issues: list[ValidationIssue]
    contract_regression_preservation: dict[str, Any] | None
    worklog: dict[str, Any]
    lane_notes: list[str]


def apply_contract_regression_preservation(
    *,
    cwd: str | Path | None,
    iteration: Any,
    state: Any,
    latex: str,
    validation_issues: list[ValidationIssue],
    worklog: dict[str, Any],
    lane_notes: list[str],
    citation_map: dict[str, Any],
    figures_dir: str | None,
    plot_manifest: dict[str, Any],
    plot_assets_index: dict[str, Any],
    experimental_log_text: str,
    expected_section_titles: list[str],
    narrative_plan: dict[str, Any],
    claim_map: dict[str, Any],
    citation_placement_plan: dict[str, Any],
) -> RefinementContractCheckResult:
    blocking_issues = _blocking_issues(validation_issues)
    contract_regression_preservation: dict[str, Any] | None = None
    if blocking_issues:
        preserved_issues = collect_paper_contract_issues(
            iteration.current_paper,
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
        if not _blocking_issues(preserved_issues):
            rejected_candidate_path = artifact_path(cwd, f"paper.refined.iter-{iteration.candidate_iter:02d}.rejected-contract.tex")
            write_text(rejected_candidate_path, latex)
            rejected_validation_path, _rejected_validation_payload = _record_validation_report(
                cwd,
                stage="refinement_rejected_contract_regression",
                issues=validation_issues,
                name=f"validation.refine.iter-{iteration.candidate_iter:02d}.rejected-contract.json",
                manuscript_text=latex,
            )
            contract_regression_preservation = {
                "preserved_prior_after_contract_regression": True,
                "rejected_candidate_path": str(rejected_candidate_path),
                "rejected_candidate_sha256": _file_sha256(rejected_candidate_path),
                "contract_regression_issue_count": len(blocking_issues),
                "contract_regression_validation_report_path": str(rejected_validation_path),
            }
            latex = iteration.current_paper
            validation_issues = preserved_issues
            blocking_issues = []
            worklog.setdefault("actions_taken", []).append(
                "Preserved the pre-refinement manuscript because the generated revision regressed citation/grounding contract checks."
            )
            lane_notes = lane_notes + ["Refinement draft regressed contract checks; preserved prior validated manuscript."]
            print(
                f"Refinement iter {state.refinement_iteration + 1} preserved prior manuscript after contract regression.",
                file=sys.stderr,
            )

    return RefinementContractCheckResult(
        latex=latex,
        validation_issues=validation_issues,
        blocking_issues=blocking_issues,
        contract_regression_preservation=contract_regression_preservation,
        worklog=worklog,
        lane_notes=lane_notes,
    )
