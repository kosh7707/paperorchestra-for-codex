from __future__ import annotations

from paperorchestra.interfaces.cli_parser_sections.authoring import register_authoring_commands
from paperorchestra.interfaces.cli_parser_sections.orchestration import register_orchestration_commands
from paperorchestra.interfaces.cli_parser_sections.quality import register_quality_commands
from paperorchestra.interfaces.cli_parser_sections.session import register_session_commands

__all__ = [
    "register_authoring_commands",
    "register_orchestration_commands",
    "register_quality_commands",
    "register_session_commands",
]
