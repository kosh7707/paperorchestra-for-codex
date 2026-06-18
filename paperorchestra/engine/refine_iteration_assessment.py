from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import write_json, write_text
from paperorchestra.core.session import artifact_path, review_path
from paperorchestra.engine.refine_candidate import review_refinement_candidate, snapshot_refinement_state
from paperorchestra.engine.refine_compile import apply_compile_acceptance_gate
from paperorchestra.engine.refine_iteration_types import PreparedRefinementDraft, RefinementCandidateAssessment
from paperorchestra.runtime.provider_base import BaseProvider


def write_and_assess_refinement_candidate(
    *,
    cwd: str | Path | None,
    provider: BaseProvider,
    runtime_mode: str,
    require_compile_for_accept: bool,
    draft: PreparedRefinementDraft,
    validation_path: Path,
    validation_payload: dict[str, Any],
) -> RefinementCandidateAssessment:
    state = draft.state
    iteration = draft.iteration
    candidate_tex_path = artifact_path(cwd, f"paper.refined.iter-{iteration.candidate_iter:02d}.tex")
    worklog_path = review_path(cwd, f"refinement_worklog.iter-{iteration.candidate_iter:02d}.json")
    write_text(candidate_tex_path, draft.latex)
    write_json(worklog_path, draft.worklog)

    candidate_snapshot = snapshot_refinement_state(state, review_payload=iteration.review_payload)
    candidate_review_state = review_refinement_candidate(
        cwd=cwd,
        provider=provider,
        state=state,
        iteration=iteration,
        candidate_tex_path=candidate_tex_path,
        latex=draft.latex,
        runtime_mode=runtime_mode,
        snapshot=candidate_snapshot,
    )
    compile_gate = apply_compile_acceptance_gate(
        enabled=require_compile_for_accept,
        cwd=cwd,
        candidate_iter=iteration.candidate_iter,
        candidate_tex_path=candidate_tex_path,
        latex=draft.latex,
        current_paper=iteration.current_paper,
        previous_review_path=candidate_snapshot.temp_latest_review or state.artifacts.latest_review_json or "",
        previous_score=candidate_snapshot.previous_score,
        previous_axes=candidate_snapshot.previous_axes,
        candidate_review_path=candidate_review_state.candidate_review_path,
        candidate_score=candidate_review_state.candidate_score,
        candidate_axes=candidate_review_state.candidate_axes,
        no_op_refinement=candidate_review_state.no_op_refinement,
        latest_compile_report_json=state.artifacts.latest_compile_report_json,
        compiled_pdf=state.artifacts.compiled_pdf,
        worklog=draft.worklog,
        lane_notes=draft.lane_notes,
    )
    return RefinementCandidateAssessment(
        validation_path=validation_path,
        validation_payload=validation_payload,
        candidate_tex_path=candidate_tex_path,
        worklog_path=worklog_path,
        latex=compile_gate.latex,
        temp_state_paper=candidate_snapshot.temp_state_paper,
        temp_latest_review=candidate_snapshot.temp_latest_review,
        temp_review_history_len=candidate_snapshot.temp_review_history_len,
        previous_score=candidate_snapshot.previous_score,
        previous_axes=candidate_snapshot.previous_axes,
        candidate_review_path=compile_gate.candidate_review_path,
        candidate_score=compile_gate.candidate_score,
        candidate_axes=compile_gate.candidate_axes,
        no_op_refinement=compile_gate.no_op_refinement,
        candidate_pdf_path=compile_gate.candidate_pdf_path,
        compile_error=compile_gate.compile_error,
        compile_preservation=compile_gate.compile_preservation,
        preserved_compile_error=compile_gate.preserved_compile_error,
        worklog=compile_gate.worklog,
        lane_notes=compile_gate.lane_notes,
    )
