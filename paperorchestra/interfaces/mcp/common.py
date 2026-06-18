from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from paperorchestra.runtime.provider_registry import get_provider

JSON = dict[str, Any]
ToolHandler = Callable[[JSON], JSON]


def default_cwd(arguments: JSON | None) -> Path:
    if arguments and arguments.get("cwd"):
        return Path(arguments["cwd"]).resolve()
    return Path.cwd()


def provider_from_args(arguments: JSON) -> Any:
    return get_provider(arguments.get("provider", "mock"), command=arguments.get("provider_command"))


def json_text(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False)


def ok(value: Any) -> JSON:
    text = value if isinstance(value, str) else json_text(value)
    return {"content": [{"type": "text", "text": text}], "isError": False}


def err(message: str) -> JSON:
    return {"content": [{"type": "text", "text": message}], "isError": True}
