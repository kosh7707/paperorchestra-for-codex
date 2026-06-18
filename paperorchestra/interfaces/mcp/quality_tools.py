from __future__ import annotations

from pathlib import Path

from paperorchestra.interfaces.mcp.common import JSON, default_cwd, ok, provider_from_args
from paperorchestra.loop_engine.quality.gate import write_quality_gate
from paperorchestra.loop_engine.quality.loop import write_quality_loop_plan
from paperorchestra.loop_engine.ralph.bridge import run_qa_loop_step
from paperorchestra.loop_engine.ralph.handoff import build_ralph_start_payload, launch_omx_ralph


def tool_quality_gate(arguments: JSON) -> JSON:
    output_path = Path(arguments["output_path"]).resolve() if arguments.get("output_path") else None
    plan_output_path = Path(arguments["plan_output_path"]).resolve() if arguments.get("plan_output_path") else None
    provider = provider_from_args(arguments) if arguments.get("auto_refine") else None
    path, payload = write_quality_gate(
        default_cwd(arguments),
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
    return ok({"path": str(path), "quality_gate": payload})


def tool_qa_loop(arguments: JSON) -> JSON:
    path, payload = write_quality_loop_plan(
        default_cwd(arguments),
        Path(arguments["output_path"]).resolve() if arguments.get("output_path") else None,
        require_live_verification=bool(arguments.get("require_live_verification", False)),
        quality_mode=arguments.get("quality_mode", "ralph"),
        max_iterations=int(arguments.get("max_iterations", 10)),
        accept_mixed_provenance=bool(arguments.get("accept_mixed_provenance", False)),
        quality_eval_input_path=arguments.get("quality_eval"),
    )
    return ok({"path": str(path), "plan": payload})


def tool_qa_loop_step(arguments: JSON) -> JSON:
    result = run_qa_loop_step(
        default_cwd(arguments),
        provider_from_args(arguments),
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
    return ok({"path": str(result.path), "execution": result.payload, "exit_code": result.exit_code})


def tool_ralph_start(arguments: JSON) -> JSON:
    cwd = default_cwd(arguments)
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
    return ok(payload)
