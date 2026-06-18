from __future__ import annotations

from pathlib import Path

from paperorchestra.core.models import InputBundle
from paperorchestra.core.session import create_session, load_session
from paperorchestra.interfaces.mcp.common import JSON, default_cwd, ok


def tool_status(arguments: JSON) -> JSON:
    return ok(load_session(default_cwd(arguments)).to_dict())


def tool_init_session(arguments: JSON) -> JSON:
    cwd = default_cwd(arguments)
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
    return ok(state.to_dict())
