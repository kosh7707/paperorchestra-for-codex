from __future__ import annotations

import os
import shutil
import tomllib
from pathlib import Path
from typing import Any


def _config_path(raw: str | Path | None = None) -> Path:
    if raw:
        return Path(raw).expanduser()
    return Path(os.environ.get("CODEX_CONFIG_PATH", "~/.codex/config.toml")).expanduser()


class CodexMcpRegistrationReader:
    """Read one MCP server registration from Codex config.toml."""

    def __init__(self, config_path: str | Path | None = None, *, server_name: str = "paperorchestra") -> None:
        self.path = _config_path(config_path)
        self.server_name = server_name

    def read(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "config_path": str(self.path),
            "registered": False,
            "enabled": None,
            "command": None,
            "args": [],
            "env": {},
            "detail": "Codex config not found.",
        }
        if not self.path.exists():
            return result
        try:
            config = tomllib.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            result["detail"] = f"Could not parse Codex config TOML: {type(exc).__name__}: {exc}"
            return result

        servers = config.get("mcp_servers")
        if not isinstance(servers, dict) or not isinstance(servers.get(self.server_name), dict):
            result["detail"] = f"No [mcp_servers.{self.server_name}] section found."
            return result

        server = servers[self.server_name]
        command = server.get("command")
        args = server.get("args", [])
        env = server.get("env", {})
        result.update(
            {
                "registered": True,
                "enabled": server.get("enabled", True),
                "command": command if isinstance(command, str) else None,
                "args": args if isinstance(args, list) else [],
                "env": env if isinstance(env, dict) else {},
                "detail": "Codex config registration found.",
            }
        )
        return result


def read_codex_mcp_registration(config_path: str | Path | None = None, *, server_name: str = "paperorchestra") -> dict[str, Any]:
    return CodexMcpRegistrationReader(config_path, server_name=server_name).read()


def _command_exists(command: str | None) -> tuple[bool, str | None]:
    if not command:
        return False, None
    if os.sep in command or (os.altsep and os.altsep in command):
        path = Path(command).expanduser()
        return path.exists() and os.access(path, os.X_OK), str(path)
    found = shutil.which(command)
    return bool(found), found
