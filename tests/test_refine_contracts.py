from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from paperorchestra.engine import refine_contracts, refine_stages
from paperorchestra.manuscript.validation_types import ValidationIssue


def issue(severity: str, message: str = "issue") -> ValidationIssue:
    return ValidationIssue(code=f"{severity}_issue", severity=severity, message=message)


def test_refine_stages_facade_reexports_contract_regression_helpers() -> None:
    assert refine_stages.RefinementContractCheckResult is refine_contracts.RefinementContractCheckResult
    assert refine_stages.apply_contract_regression_preservation is refine_contracts.apply_contract_regression_preservation


def test_contract_regression_preservation_noops_without_blockers(monkeypatch) -> None:
    def fail_collect(*_args, **_kwargs):
        raise AssertionError("prior manuscript should not be rechecked when candidate has no blockers")

    monkeypatch.setattr(refine_contracts, "collect_paper_contract_issues", fail_collect)
    result = refine_contracts.apply_contract_regression_preservation(
        cwd=None,
        iteration=SimpleNamespace(candidate_iter=2, current_paper="prior"),
        state=SimpleNamespace(refinement_iteration=1),
        latex="candidate",
        validation_issues=[issue("warning")],
        worklog={"actions_taken": []},
        lane_notes=["seed"],
        citation_map={},
        figures_dir=None,
        plot_manifest={},
        plot_assets_index={},
        experimental_log_text="",
        expected_section_titles=[],
        narrative_plan={},
        claim_map={},
        citation_placement_plan={},
    )

    assert result.latex == "candidate"
    assert result.validation_issues == [issue("warning")]
    assert result.blocking_issues == []
    assert result.contract_regression_preservation is None
    assert result.lane_notes == ["seed"]


def test_contract_regression_preservation_keeps_prior_when_candidate_regresses(
    tmp_path: Path, monkeypatch
) -> None:
    rejected_path = tmp_path / "rejected.tex"
    validation_path = tmp_path / "validation.rejected.json"

    monkeypatch.setattr(
        refine_contracts,
        "artifact_path",
        lambda cwd, name: rejected_path,
    )
    monkeypatch.setattr(refine_contracts, "_file_sha256", lambda path: "sha256:rejected")

    def fake_record_validation_report(*_args, **kwargs):
        assert kwargs["stage"] == "refinement_rejected_contract_regression"
        assert kwargs["manuscript_text"] == "candidate"
        return validation_path, {"recorded": True}

    monkeypatch.setattr(refine_contracts, "_record_validation_report", fake_record_validation_report)
    monkeypatch.setattr(
        refine_contracts,
        "collect_paper_contract_issues",
        lambda manuscript, **_kwargs: [issue("warning", "prior warning")] if manuscript == "prior" else [issue("error", "candidate error")],
    )
    result = refine_contracts.apply_contract_regression_preservation(
        cwd=tmp_path,
        iteration=SimpleNamespace(candidate_iter=7, current_paper="prior"),
        state=SimpleNamespace(refinement_iteration=6),
        latex="candidate",
        validation_issues=[issue("error", "candidate error")],
        worklog={"actions_taken": []},
        lane_notes=["seed"],
        citation_map={},
        figures_dir=None,
        plot_manifest={},
        plot_assets_index={},
        experimental_log_text="",
        expected_section_titles=[],
        narrative_plan={},
        claim_map={},
        citation_placement_plan={},
    )

    assert rejected_path.read_text(encoding="utf-8") == "candidate"
    assert result.latex == "prior"
    assert result.validation_issues == [issue("warning", "prior warning")]
    assert result.blocking_issues == []
    assert result.contract_regression_preservation == {
        "preserved_prior_after_contract_regression": True,
        "rejected_candidate_path": str(rejected_path),
        "rejected_candidate_sha256": "sha256:rejected",
        "contract_regression_issue_count": 1,
        "contract_regression_validation_report_path": str(validation_path),
    }
    assert "Preserved the pre-refinement manuscript" in result.worklog["actions_taken"][0]
    assert result.lane_notes == [
        "seed",
        "Refinement draft regressed contract checks; preserved prior validated manuscript.",
    ]


def test_contract_regression_preservation_keeps_candidate_when_prior_also_blocks(monkeypatch) -> None:
    monkeypatch.setattr(
        refine_contracts,
        "collect_paper_contract_issues",
        lambda manuscript, **_kwargs: [issue("error", f"{manuscript} still blocks")],
    )
    result = refine_contracts.apply_contract_regression_preservation(
        cwd=None,
        iteration=SimpleNamespace(candidate_iter=3, current_paper="prior"),
        state=SimpleNamespace(refinement_iteration=2),
        latex="candidate",
        validation_issues=[issue("error", "candidate still blocks")],
        worklog={"actions_taken": []},
        lane_notes=["seed"],
        citation_map={},
        figures_dir=None,
        plot_manifest={},
        plot_assets_index={},
        experimental_log_text="",
        expected_section_titles=[],
        narrative_plan={},
        claim_map={},
        citation_placement_plan={},
    )

    assert result.latex == "candidate"
    assert result.validation_issues == [issue("error", "candidate still blocks")]
    assert result.blocking_issues == [issue("error", "candidate still blocks")]
    assert result.contract_regression_preservation is None
    assert result.worklog == {"actions_taken": []}
