from __future__ import annotations

from paperorchestra.interfaces.mcp.authoring_tools import (
    tool_answer_human_needed,
    tool_compile_current_paper,
    tool_critique,
    tool_export_current,
    tool_import_prior_work,
    tool_research_prior_work,
    tool_run_pipeline,
    tool_write_sections,
)
from paperorchestra.interfaces.mcp.common import JSON, ToolHandler, err as _err, json_text as _json_text, ok as _ok
from paperorchestra.interfaces.mcp.orchestration_tools import tool_inspect_state, tool_orchestrate
from paperorchestra.interfaces.mcp.quality_tools import tool_qa_loop, tool_qa_loop_step, tool_quality_gate, tool_ralph_start
from paperorchestra.interfaces.mcp.session_tools import tool_init_session, tool_status

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
