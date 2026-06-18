from __future__ import annotations

from paperorchestra.interfaces.mcp.tool_schema import JSON, _schema

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
