from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

from .critics import write_citation_support_review, write_section_review
from .human_needed import record_human_needed_answer
from .models import InputBundle
from .orchestra_evidence import write_orchestrator_evidence_bundle
from .orchestra_executor import LocalActionExecutor
from .orchestra_omx_executor import OmxActionExecutor
from .orchestrator import OrchestraOrchestrator, inspect_state as orchestrator_inspect_state
from .pipeline import (
    compile_current_paper,
    import_prior_work,
    research_prior_work as generate_prior_work_seed,
    review_current_paper,
    run_pipeline,
    write_sections,
)
from .providers import get_citation_support_provider, get_provider
from .quality_gate import write_quality_gate
from .quality_loop import write_quality_loop_plan
from .ralph_bridge import build_ralph_start_payload, launch_omx_ralph, run_qa_loop_step
from .revisions import write_revision_suggestions
from .session import create_session, load_session

JSON = dict[str, Any]
ToolHandler = Callable[[JSON], JSON]

SERVER_INFO = {"name": "paperorchestra-mcp", "version": "0.1.0"}
MCP_PROTOCOL_SUPPORTED = {"2024-11-05", "2025-06-18"}
MCP_PROTOCOL_DEFAULT = "2024-11-05"
_CURRENT_STDIO_FRAMING = "content-length"


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


def _schema(properties: JSON, required: list[str] | None = None) -> JSON:
    schema: JSON = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


TOOLS: list[JSON] = [
    {
        "name": "status",
        "description": "Return the current PaperOrchestra session state.",
        "inputSchema": _schema({"cwd": {"type": "string"}}),
    },
    {
        "name": "init_session",
        "description": "Initialize a PaperOrchestra session from input files.",
        "inputSchema": _schema(
            {
                "cwd": {"type": "string"},
                "idea": {"type": "string"},
                "experimental_log": {"type": "string"},
                "template": {"type": "string"},
                "guidelines": {"type": "string"},
                "figures_dir": {"type": "string"},
                "cutoff_date": {"type": "string"},
                "venue": {"type": "string"},
                "page_limit": {"type": "integer"},
                "allow_outside_workspace": {"type": "boolean"},
            },
            ["idea", "experimental_log", "template", "guidelines"],
        ),
    },
    {
        "name": "inspect_state",
        "description": "Inspect material readiness and next orchestration actions without live work.",
        "inputSchema": _schema({"cwd": {"type": "string"}, "material": {"type": "string"}}),
    },
    {
        "name": "orchestrate",
        "description": "Run the orchestrator until the next bounded action or stop.",
        "inputSchema": _schema(
            {
                "cwd": {"type": "string"},
                "material": {"type": "string"},
                "execute_local": {"type": "boolean"},
                "plan_full_loop": {"type": "boolean"},
                "execute_omx": {"type": "boolean"},
                "write_evidence": {"type": "boolean"},
                "evidence_output": {"type": "string"},
            }
        ),
    },
    {
        "name": "research_prior_work",
        "description": "Generate/import a prior-work seed using the configured provider, including web-capable provider commands.",
        "inputSchema": _schema(
            {
                "cwd": {"type": "string"},
                "provider": {"type": "string"},
                "provider_command": {"type": "string"},
                "output": {"type": "string"},
                "paper": {"type": "string"},
                "artifact_repo": {"type": "string"},
                "runtime_mode": {"type": "string"},
                "source": {"type": "string"},
                "import_seed": {"type": "boolean"},
                "require_complete_metadata": {"type": "boolean"},
            }
        ),
    },
    {
        "name": "import_prior_work",
        "description": "Import a curated prior-work seed file.",
        "inputSchema": _schema(
            {"cwd": {"type": "string"}, "seed_file": {"type": "string"}, "source": {"type": "string"}, "require_complete_metadata": {"type": "boolean"}},
            ["seed_file"],
        ),
    },
    {
        "name": "write_sections",
        "description": "Draft or rewrite manuscript sections.",
        "inputSchema": _schema(
            {
                "cwd": {"type": "string"},
                "provider": {"type": "string"},
                "provider_command": {"type": "string"},
                "runtime_mode": {"type": "string"},
                "only_sections": {"anyOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
                "output_path": {"type": "string"},
                "claim_safe": {"type": "boolean"},
            }
        ),
    },
    {
        "name": "critique",
        "description": "Run whole-paper, section, and citation critics and produce revision suggestions.",
        "inputSchema": _schema(
            {
                "cwd": {"type": "string"},
                "provider": {"type": "string"},
                "provider_command": {"type": "string"},
                "source_paper": {"type": "string"},
                "output_dir": {"type": "string"},
                "runtime_mode": {"type": "string"},
                "citation_evidence_mode": {"type": "string", "enum": ["heuristic", "model", "web", "source"]},
            }
        ),
    },
    {
        "name": "quality_gate",
        "description": "Run the draft-quality gate and produce a repair plan.",
        "inputSchema": _schema(
            {
                "cwd": {"type": "string"},
                "output_path": {"type": "string"},
                "plan_output_path": {"type": "string"},
                "profile": {"type": "string"},
                "quality_mode": {"type": "string"},
                "max_iterations": {"type": "integer"},
                "require_live_verification": {"type": "boolean"},
                "accept_mixed_provenance": {"type": "boolean"},
                "auto_refine": {"type": "boolean"},
                "refine_iterations": {"type": "integer"},
                "runtime_mode": {"type": "string"},
                "require_compile_for_accept": {"type": "boolean"},
                "provider": {"type": "string"},
                "provider_command": {"type": "string"},
            }
        ),
    },
    {
        "name": "qa_loop",
        "description": "Build the next QA-loop repair plan.",
        "inputSchema": _schema(
            {
                "cwd": {"type": "string"},
                "output_path": {"type": "string"},
                "quality_eval": {"type": "string"},
                "quality_mode": {"type": "string"},
                "max_iterations": {"type": "integer"},
                "accept_mixed_provenance": {"type": "boolean"},
                "require_live_verification": {"type": "boolean"},
            }
        ),
    },
    {
        "name": "qa_loop_step",
        "description": "Execute one bounded QA-loop repair step.",
        "inputSchema": _schema(
            {
                "cwd": {"type": "string"},
                "provider": {"type": "string"},
                "provider_command": {"type": "string"},
                "quality_mode": {"type": "string"},
                "max_iterations": {"type": "integer"},
                "require_live_verification": {"type": "boolean"},
                "accept_mixed_provenance": {"type": "boolean"},
                "runtime_mode": {"type": "string"},
                "require_compile": {"type": "boolean"},
                "citation_evidence_mode": {"type": "string"},
                "citation_provider": {"type": "string"},
                "citation_provider_command": {"type": "string"},
                "quality_eval": {"type": "string"},
                "plan": {"type": "string"},
                "citation_support_review": {"type": "string"},
            }
        ),
    },
    {
        "name": "ralph_start",
        "description": "Create or launch an OMX Ralph handoff for the current QA loop.",
        "inputSchema": _schema(
            {
                "cwd": {"type": "string"},
                "output_path": {"type": "string"},
                "quality_mode": {"type": "string"},
                "max_iterations": {"type": "integer"},
                "require_live_verification": {"type": "boolean"},
                "accept_mixed_provenance": {"type": "boolean"},
                "evidence_root": {"type": "string"},
                "launch": {"type": "boolean"},
            }
        ),
    },
    {
        "name": "compile_current_paper",
        "description": "Compile the current manuscript.",
        "inputSchema": _schema({"cwd": {"type": "string"}}),
    },
    {
        "name": "answer_human_needed",
        "description": "Record an answer for a human_needed stop and optionally apply it.",
        "inputSchema": _schema(
            {
                "cwd": {"type": "string"},
                "answer": {"type": "string"},
                "packet_path": {"type": "string"},
                "review_scope": {"type": "string"},
                "intent": {"type": "string"},
                "action_id": {"type": "string"},
                "output_answer": {"type": "string"},
                "output_feedback": {"type": "string"},
                "redacted_answer_only": {"type": "boolean"},
                "apply": {"type": "boolean"},
                "imported_feedback_output": {"type": "string"},
                "provider": {"type": "string"},
                "provider_command": {"type": "string"},
                "citation_provider": {"type": "string"},
                "citation_provider_command": {"type": "string"},
                "max_supervised_iterations": {"type": "integer"},
                "quality_mode": {"type": "string"},
                "max_iterations": {"type": "integer"},
                "require_live_verification": {"type": "boolean"},
                "accept_mixed_provenance": {"type": "boolean"},
                "require_compile": {"type": "boolean"},
                "runtime_mode": {"type": "string"},
                "citation_evidence_mode": {"type": "string"},
            },
            ["answer"],
        ),
    },
    {
        "name": "run_pipeline",
        "description": "Run the full PaperOrchestra pipeline.",
        "inputSchema": _schema(
            {
                "cwd": {"type": "string"},
                "provider": {"type": "string"},
                "provider_command": {"type": "string"},
                "discovery_mode": {"type": "string"},
                "verify_mode": {"type": "string"},
                "verify_error_policy": {"type": "string"},
                "verify_fallback_mode": {"type": "string"},
                "require_live_verification": {"type": "boolean"},
                "refine_iterations": {"type": "integer"},
                "compile_paper": {"type": "boolean"},
                "runtime_mode": {"type": "string"},
            }
        ),
    },
]


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
    "run_pipeline": tool_run_pipeline,
}


def _negotiate_protocol_version(params: JSON) -> str:
    requested = params.get("protocolVersion")
    if isinstance(requested, str) and requested in MCP_PROTOCOL_SUPPORTED:
        return requested
    return MCP_PROTOCOL_DEFAULT


def _read_message() -> JSON | None:
    global _CURRENT_STDIO_FRAMING
    headers: dict[str, str] = {}
    line = sys.stdin.buffer.readline()
    while True:
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            line = sys.stdin.buffer.readline()
            continue
        if line.lstrip().startswith(b"{"):
            _CURRENT_STDIO_FRAMING = "newline"
            return json.loads(line.decode("utf-8"))
        break
    while True:
        if line in (b"\r\n", b"\n"):
            break
        decoded = line.decode("utf-8").strip()
        if ":" in decoded:
            key, value = decoded.split(":", 1)
            headers[key.strip().lower()] = value.strip()
        line = sys.stdin.buffer.readline()
        if not line:
            return None
    _CURRENT_STDIO_FRAMING = "content-length"
    length = int(headers.get("content-length", "0"))
    if length <= 0:
        return None
    return json.loads(sys.stdin.buffer.read(length).decode("utf-8"))


def _write_message(payload: JSON) -> None:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if _CURRENT_STDIO_FRAMING == "newline":
        sys.stdout.buffer.write(raw + b"\n")
    else:
        sys.stdout.buffer.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii"))
        sys.stdout.buffer.write(raw)
    sys.stdout.buffer.flush()


def _handle_request(message: JSON) -> JSON | None:
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params", {}) or {}

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": _negotiate_protocol_version(params),
                "serverInfo": SERVER_INFO,
                "capabilities": {"tools": {}},
            },
        }
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments", {}) or {}
        handler = TOOL_HANDLERS.get(name)
        if handler is None:
            return {"jsonrpc": "2.0", "id": request_id, "result": _err(f"Unknown tool: {name}")}
        try:
            result = handler(arguments)
        except Exception as exc:
            result = _err(f"{type(exc).__name__}: {exc}")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}


def main() -> int:
    while True:
        message = _read_message()
        if message is None:
            return 0
        response = _handle_request(message)
        if response is not None:
            _write_message(response)


if __name__ == "__main__":
    raise SystemExit(main())
