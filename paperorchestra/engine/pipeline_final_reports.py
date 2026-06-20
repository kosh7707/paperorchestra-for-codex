from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


def write_pipeline_final_reports(
    *,
    cwd: str | Path | None,
    stage: Any,
    outputs: dict[str, Any],
    require_live_verification: bool,
    emit: Callable[..., None],
) -> None:
    runtime_path, runtime_payload = stage.record_runtime_parity_report(cwd)
    state = stage.load_session(cwd)
    state.artifacts.latest_runtime_parity_json = str(runtime_path)
    stage.save_session(cwd, state)
    outputs.update(runtime_parity_report=str(runtime_path), runtime_parity=runtime_payload)

    fidelity_path, fidelity_payload = stage.record_fidelity_report(cwd)
    outputs.update(fidelity_report=str(fidelity_path), fidelity=fidelity_payload)

    if stage.load_session(cwd).artifacts.paper_full_tex:
        figure_path, figure_payload = stage.write_figure_placement_review(cwd)
        outputs.update(figure_placement_review=str(figure_path), figure_placement=figure_payload)
    if stage.load_session(cwd).artifacts.compiled_pdf:
        page_path, page_payload = stage.write_page_layout_review(cwd)
        outputs.update(page_layout_review=str(page_path), page_layout=page_payload)

    repro_path, repro_payload = stage.write_reproducibility_audit(
        cwd,
        require_live_verification=require_live_verification,
    )
    outputs.update(reproducibility_report=str(repro_path), reproducibility=repro_payload)
    emit(
        "pipeline",
        "completed",
        status=outputs.get("status"),
        reproducibility_verdict=repro_payload.get("verdict"),
    )


__all__ = ["write_pipeline_final_reports"]
