from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.core.session import load_session, save_session
from paperorchestra.engine.intro_related_stage import write_intro_related
from paperorchestra.engine.refine_stages import refine_current_paper
from paperorchestra.engine.section_writing_stage import write_sections
from paperorchestra.engine.completion import _provider_name
from paperorchestra.engine.planning_stages import generate_outline, plan_narrative_and_claims
from paperorchestra.engine.plot_stages import run_parallel_plot_and_literature
from paperorchestra.engine.research_verification_stage import build_bib, verify_papers
from paperorchestra.engine.reports import record_compile_environment_report, record_fidelity_report
from paperorchestra.engine.review_stages import (
    compile_current_paper,
    review_current_paper,
    write_figure_placement_review,
)
from paperorchestra.reviews.reproducibility import write_reproducibility_audit
from paperorchestra.runtime.parity import record_runtime_parity_report
from paperorchestra.runtime.providers import BaseProvider


def _emit_stage_event(stage: str, event: str, **payload: Any) -> None:
    record = {"stage": stage, "event": event}
    record.update(payload)
    print(json.dumps(record, ensure_ascii=False), file=sys.stderr)


def run_pipeline(
    cwd: str | Path | None,
    *,
    provider: BaseProvider,
    discovery_mode: str = "model",
    verify_mode: str = "live",
    verify_error_policy: str = "skip",
    verify_fallback_mode: str = "none",
    require_live_verification: bool = False,
    refine_iterations: int = 1,
    compile_paper: bool = False,
    runtime_mode: str = "compatibility",
) -> dict[str, Any]:
    if verify_fallback_mode not in {"none", "mock"}:
        raise ContractError(f"Unsupported verify fallback mode: {verify_fallback_mode}")
    outputs: dict[str, Any] = {"validation_reports": {}}
    state = load_session(cwd)
    state.latest_provider_name = _provider_name(provider)
    state.latest_runtime_mode = runtime_mode
    state.latest_verify_mode = verify_mode
    state.latest_verify_fallback_used = None
    save_session(cwd, state)
    _emit_stage_event("compile_environment", "started")
    compile_env_path, compile_env_payload = record_compile_environment_report(cwd)
    _emit_stage_event("compile_environment", "completed", path=str(compile_env_path))
    outputs["compile_environment"] = str(compile_env_path)
    outputs["compile_environment_report"] = compile_env_payload
    outputs["runtime_mode"] = runtime_mode
    _emit_stage_event("outline", "started")
    outputs["outline"] = str(generate_outline(cwd, provider, runtime_mode=runtime_mode))
    _emit_stage_event("outline", "completed", path=outputs["outline"])
    _emit_stage_event("parallel_plot_literature", "started", discovery_mode=discovery_mode)
    parallel_outputs = run_parallel_plot_and_literature(cwd, provider=provider, discovery_mode=discovery_mode, runtime_mode=runtime_mode)
    _emit_stage_event("parallel_plot_literature", "completed", candidates=parallel_outputs["candidates"], plots=parallel_outputs["plots"])
    outputs["plots"] = parallel_outputs["plots"]
    outputs["plot_captions"] = parallel_outputs["plot_captions"]
    outputs["plot_assets"] = parallel_outputs["plot_assets"]
    outputs["candidates"] = parallel_outputs["candidates"]
    try:
        _emit_stage_event("verify", "started", mode=verify_mode, on_error=verify_error_policy)
        outputs["verified"] = str(verify_papers(cwd, mode=verify_mode, on_error=verify_error_policy))
        _emit_stage_event("verify", "completed", path=outputs["verified"], mode=verify_mode)
    except ContractError as exc:
        if verify_mode == "live" and verify_fallback_mode == "mock":
            outputs["verify_live_error"] = str(exc)
            _emit_stage_event("verify", "fallback", error=str(exc), fallback_mode="mock")
            outputs["verified"] = str(verify_papers(cwd, mode="mock", on_error=verify_error_policy))
            outputs["verify_fallback_used"] = "mock"
            state = load_session(cwd)
            state.latest_verify_fallback_used = "mock"
            save_session(cwd, state)
            _emit_stage_event("verify", "completed", path=outputs["verified"], mode="mock")
        else:
            raise
    _emit_stage_event("build_bib", "started")
    outputs["bib"] = str(build_bib(cwd))
    _emit_stage_event("build_bib", "completed", path=outputs["bib"])
    _emit_stage_event("narrative_planning", "started")
    narrative_paths = plan_narrative_and_claims(cwd, provider, runtime_mode=runtime_mode)
    outputs["narrative_plan"] = str(narrative_paths["narrative_plan"])
    outputs["claim_map"] = str(narrative_paths["claim_map"])
    outputs["citation_placement_plan"] = str(narrative_paths["citation_placement_plan"])
    _emit_stage_event("narrative_planning", "completed", path=outputs["narrative_plan"])
    _emit_stage_event("intro_related", "started")
    outputs["intro_related"] = str(write_intro_related(cwd, provider, runtime_mode=runtime_mode))
    _emit_stage_event("intro_related", "completed", path=outputs["intro_related"])
    outputs["validation_reports"]["intro_related"] = load_session(cwd).artifacts.latest_validation_json
    _emit_stage_event("write_sections", "started")
    outputs["paper"] = str(write_sections(cwd, provider, runtime_mode=runtime_mode))
    _emit_stage_event("write_sections", "completed", path=outputs["paper"])
    outputs["validation_reports"]["section_writing"] = load_session(cwd).artifacts.latest_validation_json
    if compile_paper:
        _emit_stage_event("compile", "started")
        outputs["compiled_pdf"] = str(compile_current_paper(cwd))
        _emit_stage_event("compile", "completed", path=outputs["compiled_pdf"])
    _emit_stage_event("review", "started")
    outputs["review"] = str(review_current_paper(cwd, provider, runtime_mode=runtime_mode))
    _emit_stage_event("review", "completed", path=outputs["review"])
    _emit_stage_event("refine", "started", iterations=refine_iterations)
    outputs["refine"] = refine_current_paper(
        cwd,
        provider,
        iterations=refine_iterations,
        require_compile_for_accept=compile_paper,
        runtime_mode=runtime_mode,
    )
    outputs["validation_reports"]["refinement"] = [
        item.get("validation_report_path") for item in outputs["refine"] if item.get("validation_report_path")
    ]
    _emit_stage_event("refine", "completed", accepted=sum(1 for item in outputs["refine"] if item.get("accepted")), total=len(outputs["refine"]))
    state = load_session(cwd)
    blocked = refine_iterations > 0 and bool(outputs["refine"]) and not any(item.get("accepted", False) for item in outputs["refine"])
    if blocked:
        state.current_phase = "blocked"
        state.notes.append("Pipeline run halted because refinement was rejected.")
        outputs["status"] = "blocked"
    else:
        if compile_paper and state.artifacts.compiled_pdf:
            state.current_phase = "complete"
            state.notes.append("Pipeline run completed with compiled output.")
            outputs["status"] = "complete"
        else:
            state.current_phase = "draft_complete"
            state.notes.append("Pipeline run completed at draft stage without compiled output.")
            outputs["status"] = "draft_complete"
    save_session(cwd, state)
    runtime_parity_path, runtime_parity_payload = record_runtime_parity_report(cwd)
    state = load_session(cwd)
    state.artifacts.latest_runtime_parity_json = str(runtime_parity_path)
    save_session(cwd, state)
    outputs["runtime_parity_report"] = str(runtime_parity_path)
    outputs["runtime_parity"] = runtime_parity_payload
    fidelity_path, fidelity_payload = record_fidelity_report(cwd)
    outputs["fidelity_report"] = str(fidelity_path)
    outputs["fidelity"] = fidelity_payload
    if load_session(cwd).artifacts.paper_full_tex:
        figure_review_path, figure_review_payload = write_figure_placement_review(cwd)
        outputs["figure_placement_review"] = str(figure_review_path)
        outputs["figure_placement"] = figure_review_payload
    reproducibility_path, reproducibility_payload = write_reproducibility_audit(
        cwd,
        require_live_verification=require_live_verification,
    )
    outputs["reproducibility_report"] = str(reproducibility_path)
    outputs["reproducibility"] = reproducibility_payload
    _emit_stage_event("pipeline", "completed", status=outputs.get("status"), reproducibility_verdict=reproducibility_payload.get("verdict"))
    return outputs
