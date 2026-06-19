from __future__ import annotations

from paperorchestra.interfaces.mcp.authoring_tool_definitions import AUTHORING_TOOLS
from paperorchestra.interfaces.mcp.handlers import TOOL_HANDLERS
from paperorchestra.interfaces.mcp.quality_tool_definitions import QUALITY_TOOLS
from paperorchestra.interfaces.mcp.server_stdio import (
    JSON,
    MCP_PROTOCOL_DEFAULT,
    MCP_PROTOCOL_SUPPORTED,
    _err,
    _negotiate_protocol_version,
    _read_message,
    _write_message,
    serve_stdio,
)
from paperorchestra.interfaces.mcp.tool_schema import _schema

SESSION_TOOLS: list[JSON] = [
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
]

UTILITY_TOOLS: list[JSON] = [
    {
        "name": "export_current",
        "description": "Copy current manuscript outputs to a destination directory.",
        "inputSchema": _schema(
            {
                "cwd": {"type": "string"},
                "output": {"type": "string"},
                "include_all_artifacts": {"type": "boolean"},
            },
            ["output"],
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

TOOLS: list[JSON] = [
    *SESSION_TOOLS,
    *AUTHORING_TOOLS,
    *QUALITY_TOOLS,
    *UTILITY_TOOLS,
]

SERVER_INFO = {"name": "paperorchestra-mcp", "version": "0.1.0"}


def _handle_request(message: JSON) -> JSON | None:
    from paperorchestra.interfaces.mcp.server_stdio import _handle_request as handle_request

    return handle_request(message, tools=TOOLS, handlers=TOOL_HANDLERS, server_info=SERVER_INFO)


def main() -> int:
    return serve_stdio(tools=TOOLS, handlers=TOOL_HANDLERS, server_info=SERVER_INFO)


if __name__ == "__main__":
    raise SystemExit(main())
