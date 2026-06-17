from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

from paperorchestra.core.io import read_json
from paperorchestra.core.session import build_path
from paperorchestra.manuscript.latex import compile_latex


@dataclass(frozen=True)
class RefinementCompileGateResult:
    latex: str
    candidate_pdf_path: str | Path | None
    compile_error: str | None
    compile_preservation: bool
    preserved_compile_error: str | None
    candidate_review_path: Path
    candidate_score: float
    candidate_axes: dict[str, float]
    no_op_refinement: bool
    worklog: dict[str, Any]
    lane_notes: list[str]


def _previous_compile_was_clean(latest_compile_report_json: str | None) -> bool:
    if not latest_compile_report_json:
        return False
    path = Path(latest_compile_report_json)
    if not path.exists():
        return False
    previous_compile_report = read_json(path)
    return (
        isinstance(previous_compile_report, dict)
        and bool(previous_compile_report.get("clean"))
        and bool(previous_compile_report.get("pdf_exists"))
    )


def apply_compile_acceptance_gate(
    *,
    enabled: bool,
    cwd: str | Path | None,
    candidate_iter: int,
    candidate_tex_path: str | Path,
    latex: str,
    current_paper: str,
    previous_review_path: str | Path | None,
    previous_score: float,
    previous_axes: dict[str, float],
    candidate_review_path: str | Path,
    candidate_score: float,
    candidate_axes: dict[str, float],
    no_op_refinement: bool,
    latest_compile_report_json: str | None,
    compiled_pdf: str | Path | None,
    worklog: dict[str, Any],
    lane_notes: list[str],
) -> RefinementCompileGateResult:
    candidate_pdf_path: str | Path | None = None
    compile_error: str | None = None
    preserved_compile_error: str | None = None
    compile_preservation = False

    if enabled:
        try:
            candidate_pdf_path = compile_latex(
                candidate_tex_path,
                workdir=build_path(cwd, f"compiled-iter-{candidate_iter:02d}"),
                output_log=build_path(cwd, f"latex-build.iter-{candidate_iter:02d}.log"),
            )
        except Exception as exc:
            compile_error = str(exc)
            preserved_compile_error = compile_error
            if _previous_compile_was_clean(latest_compile_report_json):
                latex = current_paper
                candidate_pdf_path = compiled_pdf
                compile_error = None
                compile_preservation = True
                no_op_refinement = True
                candidate_review_path = Path(previous_review_path or "")
                candidate_score = previous_score
                candidate_axes = previous_axes
                worklog.setdefault("actions_taken", []).append(
                    "Preserved the pre-refinement compiled manuscript because the generated revision failed compile acceptance."
                )
                lane_notes = lane_notes + ["Refinement revision failed compile acceptance; preserved prior compiled manuscript."]
                print(
                    f"Refinement iter {candidate_iter} preserved prior compiled manuscript after compile failure.",
                    file=sys.stderr,
                )

    return RefinementCompileGateResult(
        latex=latex,
        candidate_pdf_path=candidate_pdf_path,
        compile_error=compile_error,
        compile_preservation=compile_preservation,
        preserved_compile_error=preserved_compile_error,
        candidate_review_path=Path(candidate_review_path),
        candidate_score=candidate_score,
        candidate_axes=candidate_axes,
        no_op_refinement=no_op_refinement,
        worklog=worklog,
        lane_notes=lane_notes,
    )
