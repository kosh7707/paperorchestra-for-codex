from __future__ import annotations

from paperorchestra.interfaces.mcp.authoring_tool_definitions import AUTHORING_TOOLS
from paperorchestra.interfaces.mcp.quality_tool_definitions import QUALITY_TOOLS
from paperorchestra.interfaces.mcp.session_tool_definitions import SESSION_TOOLS
from paperorchestra.interfaces.mcp.tool_schema import JSON, _schema
from paperorchestra.interfaces.mcp.utility_tool_definitions import UTILITY_TOOLS

TOOLS: list[JSON] = [
    *SESSION_TOOLS,
    *AUTHORING_TOOLS,
    *QUALITY_TOOLS,
    *UTILITY_TOOLS,
]

__all__ = ["JSON", "TOOLS", "_schema"]
