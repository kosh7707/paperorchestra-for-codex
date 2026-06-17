from __future__ import annotations

from pathlib import Path

import pytest

from paperorchestra.core.session import set_current_session
from paperorchestra.engine import refine_compile, refine_stages


def test_refine_stages_facade_reexports_compile_gate() -> None:
    assert refine_stages.RefinementCompileGateResult is refine_compile.RefinementCompileGateResult
    assert refine_stages.apply_compile_acceptance_gate is refine_compile.apply_compile_acceptance_gate


def test_compile_gate_disabled_preserves_candidate_without_compiling(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_compile(*_args, **_kwargs):
        raise AssertionError("compile_latex should not be called when gate is disabled")

    monkeypatch.setattr(refine_compile, "compile_latex", fail_compile)
    result = refine_compile.apply_compile_acceptance_gate(
        enabled=False,
        cwd=None,
        candidate_iter=2,
        candidate_tex_path=Path("candidate.tex"),
        latex="candidate",
        current_paper="previous",
        previous_review_path="review.latest.json",
        previous_score=4.0,
        previous_axes={"clarity": 4.0},
        candidate_review_path=Path("review.candidate.json"),
        candidate_score=4.2,
        candidate_axes={"clarity": 4.2},
        no_op_refinement=False,
        latest_compile_report_json=None,
        compiled_pdf=None,
        worklog={"actions_taken": []},
        lane_notes=["seed"],
    )

    assert result.latex == "candidate"
    assert result.candidate_pdf_path is None
    assert result.compile_error is None
    assert result.compile_preservation is False
    assert result.preserved_compile_error is None
    assert result.candidate_review_path == Path("review.candidate.json")
    assert result.candidate_score == 4.2
    assert result.no_op_refinement is False
    assert result.lane_notes == ["seed"]


def test_compile_gate_preserves_prior_clean_compile_after_candidate_compile_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    set_current_session(tmp_path, "session-1")
    previous_compile_report = tmp_path / "compile-report.json"
    previous_compile_report.write_text('{"clean": true, "pdf_exists": true}\n', encoding="utf-8")
    candidate = tmp_path / "candidate.tex"
    candidate.write_text("candidate", encoding="utf-8")

    def fail_compile(*_args, **_kwargs):
        raise RuntimeError("latex exploded")

    monkeypatch.setattr(refine_compile, "compile_latex", fail_compile)
    worklog: dict[str, list[str]] = {"actions_taken": []}
    result = refine_compile.apply_compile_acceptance_gate(
        enabled=True,
        cwd=tmp_path,
        candidate_iter=3,
        candidate_tex_path=candidate,
        latex="candidate",
        current_paper="previous",
        previous_review_path="review.latest.json",
        previous_score=4.0,
        previous_axes={"clarity": 4.0},
        candidate_review_path=Path("review.candidate.json"),
        candidate_score=2.0,
        candidate_axes={"clarity": 2.0},
        no_op_refinement=False,
        latest_compile_report_json=str(previous_compile_report),
        compiled_pdf="paper.pdf",
        worklog=worklog,
        lane_notes=["seed"],
    )

    assert result.latex == "previous"
    assert result.candidate_pdf_path == "paper.pdf"
    assert result.compile_error is None
    assert result.preserved_compile_error == "latex exploded"
    assert result.compile_preservation is True
    assert result.no_op_refinement is True
    assert result.candidate_review_path == Path("review.latest.json")
    assert result.candidate_score == 4.0
    assert result.candidate_axes == {"clarity": 4.0}
    assert "Preserved the pre-refinement compiled manuscript" in worklog["actions_taken"][0]
    assert result.lane_notes == [
        "seed",
        "Refinement revision failed compile acceptance; preserved prior compiled manuscript.",
    ]
