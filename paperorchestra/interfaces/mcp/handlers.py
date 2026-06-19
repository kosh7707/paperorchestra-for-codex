from __future__ import annotations

from pathlib import Path

from paperorchestra.core.models import InputBundle
from paperorchestra.core.session import create_session, load_session
from paperorchestra.interfaces.mcp.authoring_tools import (
    tool_answer_human_needed,
    tool_authoring_round,
    tool_compile_current_paper,
    tool_critique,
    tool_export_current,
    tool_import_prior_work,
    tool_research_prior_work,
    tool_run_pipeline,
    tool_write_sections,
)
from paperorchestra.interfaces.mcp.common import JSON, ToolHandler, default_cwd, ok
from paperorchestra.interfaces.mcp.quality_tools import tool_qa_loop, tool_qa_loop_step, tool_quality_gate, tool_ralph_start
from paperorchestra.orchestra.controller import OrchestraOrchestrator, inspect_state as orchestrator_inspect_state
from paperorchestra.orchestra.evidence import write_orchestrator_evidence_bundle
from paperorchestra.orchestra.executor import LocalActionExecutor
from paperorchestra.orchestra.omx_action_executor import OmxActionExecutor


def tool_status(arguments: JSON) -> JSON:
    return ok(load_session(default_cwd(arguments)).to_dict())


def tool_init_session(arguments: JSON) -> JSON:
    cwd = default_cwd(arguments)
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
    return ok(state.to_dict())


def tool_inspect_state(arguments: JSON) -> JSON:
    return ok(
        orchestrator_inspect_state(
            default_cwd(arguments),
            material_path=arguments.get("material"),
        ).to_public_dict()
    )


def _make_omx_executor(cwd: Path, *, timeout_seconds: float = 30.0) -> OmxActionExecutor:
    return OmxActionExecutor(cwd=cwd, timeout_seconds=timeout_seconds)


def tool_orchestrate(arguments: JSON) -> JSON:
    cwd = default_cwd(arguments)
    orchestrator = OrchestraOrchestrator(cwd)
    modes = [
        bool(arguments.get("execute_local")),
        bool(arguments.get("plan_full_loop")),
        bool(arguments.get("execute_omx")),
    ]
    if sum(modes) > 1:
        raise ValueError("execute_local, plan_full_loop, and execute_omx are mutually exclusive.")
    if arguments.get("execute_local"):
        result = orchestrator.step(
            material_path=arguments.get("material"),
            execute=True,
            executor=LocalActionExecutor(material_path=arguments.get("material")),
        )
    elif arguments.get("plan_full_loop"):
        result = orchestrator.plan_full_loop(material_path=arguments.get("material"))
    elif arguments.get("execute_omx"):
        result = orchestrator.execute_omx_once(
            material_path=arguments.get("material"),
            executor=_make_omx_executor(cwd),
        )
    else:
        result = orchestrator.run_until_blocked(material_path=arguments.get("material"))
    payload = result.to_public_dict()
    if arguments.get("write_evidence"):
        payload["evidence_bundle"] = write_orchestrator_evidence_bundle(
            cwd,
            result.state,
            output_dir=arguments.get("evidence_output"),
        )
    return ok(payload)


TOOL_HANDLERS: dict[str, ToolHandler] = {
    "status": tool_status,
    "init_session": tool_init_session,
    "inspect_state": tool_inspect_state,
    "orchestrate": tool_orchestrate,
    "research_prior_work": tool_research_prior_work,
    "import_prior_work": tool_import_prior_work,
    "authoring_round": tool_authoring_round,
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
