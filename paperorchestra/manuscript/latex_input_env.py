from __future__ import annotations

import os
from pathlib import Path


def _prepend_path(env: dict[str, str], key: str, *paths: Path) -> None:
    existing = env.get(key, "")
    parts = [str(path) for path in paths if str(path)]
    if existing:
        parts.append(existing)
        env[key] = os.pathsep.join(parts)
    elif parts:
        env[key] = os.pathsep.join(parts) + os.pathsep


def _force_latexmk_rerun_command(full_cmd: list[str]) -> list[str]:
    if "latexmk" not in full_cmd:
        return list(full_cmd)
    command = list(full_cmd)
    if "-g" not in command:
        insert_at = command.index("latexmk") + 1
        command.insert(insert_at, "-g")
    return command
