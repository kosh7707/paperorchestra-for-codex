from __future__ import annotations

from paperorchestra.interfaces.mcp.authoring_tool_definitions import AUTHORING_TOOLS
from paperorchestra.interfaces.mcp.handlers import TOOL_HANDLERS


def test_mcp_exports_visual_audit_tool_with_imported_findings_path() -> None:
    tools = {tool["name"]: tool for tool in AUTHORING_TOOLS}

    assert "visual_audit" in tools
    assert "visual_audit" in TOOL_HANDLERS
    properties = tools["visual_audit"]["inputSchema"]["properties"]
    assert {"cwd", "pdf", "output", "render_dir", "findings_json"} <= set(properties)
