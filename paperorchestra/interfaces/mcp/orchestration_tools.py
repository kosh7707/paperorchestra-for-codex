from __future__ import annotations

from pathlib import Path

from paperorchestra.interfaces.mcp.common import JSON, default_cwd, ok
from paperorchestra.orchestra.controller import OrchestraOrchestrator, inspect_state as orchestrator_inspect_state
from paperorchestra.orchestra.evidence import write_orchestrator_evidence_bundle
from paperorchestra.orchestra.executor import LocalActionExecutor
from paperorchestra.orchestra.omx_action_executor import OmxActionExecutor


def tool_inspect_state(arguments: JSON) -> JSON:
    return ok(orchestrator_inspect_state(default_cwd(arguments), material_path=arguments.get("material")).to_public_dict())


def _make_omx_executor(cwd: Path, *, timeout_seconds: float = 30.0) -> OmxActionExecutor:
    return OmxActionExecutor(cwd=cwd, timeout_seconds=timeout_seconds)


def tool_orchestrate(arguments: JSON) -> JSON:
    cwd = default_cwd(arguments)
    orchestrator = OrchestraOrchestrator(cwd)
    modes = [bool(arguments.get("execute_local")), bool(arguments.get("plan_full_loop")), bool(arguments.get("execute_omx"))]
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
        result = orchestrator.execute_omx_once(material_path=arguments.get("material"), executor=_make_omx_executor(cwd))
    else:
        result = orchestrator.run_until_blocked(material_path=arguments.get("material"))
    payload = result.to_public_dict()
    if arguments.get("write_evidence"):
        payload["evidence_bundle"] = write_orchestrator_evidence_bundle(cwd, result.state, output_dir=arguments.get("evidence_output"))
    return ok(payload)
