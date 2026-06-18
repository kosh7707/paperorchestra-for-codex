from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from paperorchestra.reviews.critics import write_citation_support_review, write_section_review
from paperorchestra.interfaces.exporting import export_current_artifacts
from paperorchestra.feedback.human_needed import record_human_needed_answer
from paperorchestra.core.models import InputBundle
from paperorchestra.orchestra.evidence import write_orchestrator_evidence_bundle
from paperorchestra.orchestra.executor import LocalActionExecutor
from paperorchestra.orchestra.omx_action_executor import OmxActionExecutor
from paperorchestra.orchestra.controller import OrchestraOrchestrator, inspect_state as orchestrator_inspect_state
from paperorchestra.engine.pipeline import run_pipeline
from paperorchestra.engine.research_prior_work_stage import import_prior_work, research_prior_work as generate_prior_work_seed
from paperorchestra.engine.review_stages import compile_current_paper, review_current_paper
from paperorchestra.engine.section_writing_stage import write_sections
from paperorchestra.runtime.providers import get_citation_support_provider, get_provider
from paperorchestra.loop_engine.quality.gate import write_quality_gate
from paperorchestra.loop_engine.quality.loop import write_quality_loop_plan
from paperorchestra.loop_engine.ralph.bridge import run_qa_loop_step
from paperorchestra.loop_engine.ralph.handoff import build_ralph_start_payload, launch_omx_ralph
from paperorchestra.manuscript.revisions import write_revision_suggestions
from paperorchestra.core.session import create_session, load_session

JSON = dict[str, Any]
ToolHandler = Callable[[JSON], JSON]


def _default_cwd(arguments: JSON | None) -> Path:
    if arguments and arguments.get("cwd"):
        return Path(arguments["cwd"]).resolve()
    return Path.cwd()


def _provider_from_args(arguments: JSON) -> Any:
    return get_provider(arguments.get("provider", "mock"), command=arguments.get("provider_command"))


def _json_text(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False)


def _ok(value: Any) -> JSON:
    text = value if isinstance(value, str) else _json_text(value)
    return {"content": [{"type": "text", "text": text}], "isError": False}


def _err(message: str) -> JSON:
    return {"content": [{"type": "text", "text": message}], "isError": True}


def tool_status(arguments: JSON) -> JSON:
    return _ok(load_session(_default_cwd(arguments)).to_dict())


def tool_init_session(arguments: JSON) -> JSON:
    cwd = _default_cwd(arguments)
    state = create_session(
        cwd,
        InputBundle(
            idea_path=str(Path(arguments["idea"]).resolve()),
            experimental_log_path=str(Path(arguments["experimental_log"]).resolve()),
            template_path=str(Path(arguments["template"]).resolve()),
            guidelines_path=str(Path(arguments["guidelines"]).resolve()),
            figures_dir=str(Path(arguments["figures_dir"]).resolve()) if arguments.get("figures_dir") else None,
            cutoff_date=arguments.get("cutoff_date"),
            venue=arguments.get("venue"),
            page_limit=arguments.get("page_limit"),
        ),
        allow_outside_workspace=bool(arguments.get("allow_outside_workspace", False)),
    )
    return _ok(state.to_dict())


def tool_inspect_state(arguments: JSON) -> JSON:
    return _ok(orchestrator_inspect_state(_default_cwd(arguments), material_path=arguments.get("material")).to_public_dict())


def _make_omx_executor(cwd: Path, *, timeout_seconds: float = 30.0) -> OmxActionExecutor:
    return OmxActionExecutor(cwd=cwd, timeout_seconds=timeout_seconds)


def tool_orchestrate(arguments: JSON) -> JSON:
    cwd = _default_cwd(arguments)
    orchestrator = OrchestraOrchestrator(cwd)
    modes = [bool(arguments.get("execute_local")), bool(arguments.get("plan_full_loop")), bool(arguments.get("execute_omx"))]
    if sum(modes) > 1:
        raise ValueError("execute_local, plan_full_loop, and execute_omx are mutually exclusive.")
    if arguments.get("execute_local"):
        result = orchestrator.step(material_path=arguments.get("material"), execute=True, executor=LocalActionExecutor(material_path=arguments.get("material")))
    elif arguments.get("plan_full_loop"):
        result = orchestrator.plan_full_loop(material_path=arguments.get("material"))
    elif arguments.get("execute_omx"):
        result = orchestrator.execute_omx_once(material_path=arguments.get("material"), executor=_make_omx_executor(cwd))
    else:
        result = orchestrator.run_until_blocked(material_path=arguments.get("material"))
    payload = result.to_public_dict()
    if arguments.get("write_evidence"):
        payload["evidence_bundle"] = write_orchestrator_evidence_bundle(cwd, result.state, output_dir=arguments.get("evidence_output"))
    return _ok(payload)



def tool_research_prior_work(arguments: JSON) -> JSON:
    cwd = _default_cwd(arguments)
    return _ok(
        generate_prior_work_seed(
            cwd,
            _provider_from_args(arguments),
            output=arguments.get("output"),
            paper=arguments.get("paper"),
            artifact_repo=arguments.get("artifact_repo"),
            runtime_mode=arguments.get("runtime_mode", "compatibility"),
            source=arguments.get("source", "codex_web_seed"),
            import_seed=bool(arguments.get("import_seed", False)),
            require_complete_metadata=bool(arguments.get("require_complete_metadata", False)),
        )
    )


def tool_import_prior_work(arguments: JSON) -> JSON:
    return _ok(
        import_prior_work(
            _default_cwd(arguments),
            seed_file=arguments["seed_file"],
            source=arguments.get("source", "manual_seed"),
            require_complete_metadata=bool(arguments.get("require_complete_metadata", False)),
        )
    )


def tool_write_sections(arguments: JSON) -> JSON:
    cwd = _default_cwd(arguments)
    return _ok(
        {
            "path": str(
                write_sections(
                    cwd,
                    _provider_from_args(arguments),
                    runtime_mode=arguments.get("runtime_mode", "compatibility"),
                    only_sections=arguments.get("only_sections"),
                    output_path=arguments.get("output_path"),
                    claim_safe=bool(arguments.get("claim_safe", False)),
                )
            )
        }
    )


def tool_critique(arguments: JSON) -> JSON:
    cwd = _default_cwd(arguments)
    provider = _provider_from_args(arguments)
    state = load_session(cwd)
    output_dir = Path(arguments["output_dir"]).resolve() if arguments.get("output_dir") else Path(state.artifacts.paper_full_tex or state.inputs.idea_path).resolve().parent
    output_dir.mkdir(parents=True, exist_ok=True)
    review_path = review_current_paper(cwd, provider, runtime_mode=arguments.get("runtime_mode", "compatibility"))
    section_path = write_section_review(cwd, output_dir / "section_review.json")
    evidence_mode = arguments.get("citation_evidence_mode") or "heuristic"
    citation_provider = get_citation_support_provider(arguments.get("provider", "mock"), command=arguments.get("provider_command"), evidence_mode=evidence_mode)
    citation_path = write_citation_support_review(cwd, output_dir / "citation_support_review.json", provider=citation_provider, evidence_mode=evidence_mode)
    suggestions_path = write_revision_suggestions(
        arguments.get("source_paper") or state.artifacts.paper_full_tex,
        review_path,
        output_dir / "revision_suggestions.json",
        section_review_json=section_path,
        citation_review_json=citation_path,
    )
    return _ok({"review": str(review_path), "section_review": str(section_path), "citation_support_review": str(citation_path), "revision_suggestions": str(suggestions_path)})


def tool_quality_gate(arguments: JSON) -> JSON:
    output_path = Path(arguments["output_path"]).resolve() if arguments.get("output_path") else None
    plan_output_path = Path(arguments["plan_output_path"]).resolve() if arguments.get("plan_output_path") else None
    provider = _provider_from_args(arguments) if arguments.get("auto_refine") else None
    path, payload = write_quality_gate(
        _default_cwd(arguments),
        output_path,
        plan_output_path=plan_output_path,
        profile=arguments.get("profile", "auto"),
        quality_mode=arguments.get("quality_mode", "draft"),
        require_live_verification=bool(arguments.get("require_live_verification", False)),
        accept_mixed_provenance=bool(arguments.get("accept_mixed_provenance", False)),
        max_iterations=int(arguments.get("max_iterations", 10)),
        auto_refine=bool(arguments.get("auto_refine", False)),
        provider=provider,
        refine_iterations=int(arguments.get("refine_iterations", 1)),
        runtime_mode=arguments.get("runtime_mode", "compatibility"),
        require_compile_for_accept=bool(arguments.get("require_compile_for_accept", False)),
    )
    return _ok({"path": str(path), "quality_gate": payload})


def tool_qa_loop(arguments: JSON) -> JSON:
    path, payload = write_quality_loop_plan(
        _default_cwd(arguments),
        Path(arguments["output_path"]).resolve() if arguments.get("output_path") else None,
        require_live_verification=bool(arguments.get("require_live_verification", False)),
        quality_mode=arguments.get("quality_mode", "ralph"),
        max_iterations=int(arguments.get("max_iterations", 10)),
        accept_mixed_provenance=bool(arguments.get("accept_mixed_provenance", False)),
        quality_eval_input_path=arguments.get("quality_eval"),
    )
    return _ok({"path": str(path), "plan": payload})


def tool_qa_loop_step(arguments: JSON) -> JSON:
    result = run_qa_loop_step(
        _default_cwd(arguments),
        _provider_from_args(arguments),
        quality_mode=arguments.get("quality_mode", "claim_safe"),
        max_iterations=int(arguments.get("max_iterations", 10)),
        require_live_verification=bool(arguments.get("require_live_verification", False)),
        accept_mixed_provenance=bool(arguments.get("accept_mixed_provenance", False)),
        runtime_mode=arguments.get("runtime_mode", "compatibility"),
        require_compile=bool(arguments.get("require_compile", False)),
        citation_evidence_mode=arguments.get("citation_evidence_mode", "web"),
        citation_provider_name=arguments.get("citation_provider"),
        citation_provider_command=arguments.get("citation_provider_command"),
        quality_eval_input_path=arguments.get("quality_eval"),
        qa_loop_plan_input_path=arguments.get("plan"),
        citation_support_review_path=arguments.get("citation_support_review"),
    )
    return _ok({"path": str(result.path), "execution": result.payload, "exit_code": result.exit_code})


def tool_ralph_start(arguments: JSON) -> JSON:
    cwd = _default_cwd(arguments)
    payload = build_ralph_start_payload(
        cwd,
        quality_mode=arguments.get("quality_mode", "claim_safe"),
        max_iterations=int(arguments.get("max_iterations", 10)),
        output_path=Path(arguments["output_path"]).resolve() if arguments.get("output_path") else None,
        require_live_verification=bool(arguments.get("require_live_verification", False)),
        accept_mixed_provenance=bool(arguments.get("accept_mixed_provenance", False)),
        evidence_root=arguments.get("evidence_root"),
    )
    if arguments.get("launch"):
        proc = launch_omx_ralph(payload["argv"], cwd=cwd)
        payload["launch"] = {"pid": proc.pid, "status": "started"}
    else:
        payload["launch"] = {"status": "dry_run"}
    return _ok(payload)


def tool_compile_current_paper(arguments: JSON) -> JSON:
    return _ok({"path": str(compile_current_paper(_default_cwd(arguments)))})


def tool_answer_human_needed(arguments: JSON) -> JSON:
    provider = _provider_from_args(arguments) if arguments.get("apply") else None
    payload = record_human_needed_answer(
        _default_cwd(arguments),
        str(arguments.get("answer") or ""),
        packet_path=arguments.get("packet_path"),
        review_scope=arguments.get("review_scope"),
        intent=arguments.get("intent"),
        action_id=arguments.get("action_id"),
        output_answer=arguments.get("output_answer"),
        output_feedback=arguments.get("output_feedback"),
        redacted_answer_only=bool(arguments.get("redacted_answer_only", False)),
        apply=bool(arguments.get("apply", False)),
        imported_feedback_output=arguments.get("imported_feedback_output"),
        provider=provider,
        max_supervised_iterations=int(arguments.get("max_supervised_iterations", 1)),
        require_compile=bool(arguments.get("require_compile", False)),
        quality_mode=arguments.get("quality_mode", "claim_safe"),
        max_iterations=int(arguments.get("max_iterations", 10)),
        require_live_verification=bool(arguments.get("require_live_verification", False)),
        accept_mixed_provenance=bool(arguments.get("accept_mixed_provenance", False)),
        runtime_mode=arguments.get("runtime_mode", "compatibility"),
        citation_evidence_mode=arguments.get("citation_evidence_mode", "web"),
        citation_provider_name=arguments.get("citation_provider"),
        citation_provider_command=arguments.get("citation_provider_command"),
    )
    return _ok(payload)



def tool_export_current(arguments: JSON) -> JSON:
    return _ok(
        export_current_artifacts(
            _default_cwd(arguments),
            arguments["output"],
            include_all_artifacts=bool(arguments.get("include_all_artifacts", False)),
        )
    )


def tool_run_pipeline(arguments: JSON) -> JSON:
    cwd = _default_cwd(arguments)
    return _ok(
        run_pipeline(
            cwd,
            provider=_provider_from_args(arguments),
            discovery_mode=arguments.get("discovery_mode", "model"),
            verify_mode=arguments.get("verify_mode", "live"),
            verify_error_policy=arguments.get("verify_error_policy", "skip"),
            verify_fallback_mode=arguments.get("verify_fallback_mode", "none"),
            require_live_verification=bool(arguments.get("require_live_verification", False)),
            refine_iterations=int(arguments.get("refine_iterations", 1)),
            compile_paper=bool(arguments.get("compile_paper", False)),
            runtime_mode=arguments.get("runtime_mode", "compatibility"),
        )
    )


TOOL_HANDLERS: dict[str, ToolHandler] = {
    "status": tool_status,
    "init_session": tool_init_session,
    "inspect_state": tool_inspect_state,
    "orchestrate": tool_orchestrate,
    "research_prior_work": tool_research_prior_work,
    "import_prior_work": tool_import_prior_work,
    "write_sections": tool_write_sections,
    "critique": tool_critique,
    "quality_gate": tool_quality_gate,
    "qa_loop": tool_qa_loop,
    "qa_loop_step": tool_qa_loop_step,
    "ralph_start": tool_ralph_start,
    "compile_current_paper": tool_compile_current_paper,
    "answer_human_needed": tool_answer_human_needed,
    "export_current": tool_export_current,
    "run_pipeline": tool_run_pipeline,
}
