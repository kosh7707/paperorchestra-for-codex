from __future__ import annotations

from paperorchestra.interfaces.mcp.tool_schema import JSON, _schema

QUALITY_TOOLS: list[JSON] = [
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
]
