from __future__ import annotations

from paperorchestra.interfaces.mcp.tool_schema import JSON, _schema

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
