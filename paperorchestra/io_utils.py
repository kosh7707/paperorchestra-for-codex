from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


CODE_BLOCK_RE = re.compile(r"```(?:json|latex|bibtex)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


class ExtractionError(ValueError):
    pass


def read_text(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def write_text(path: str | Path, content: str) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_name(f".{destination.name}.tmp.{os.getpid()}")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, destination)


def write_json(path: str | Path, data: Any) -> None:
    write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def read_json(path: str | Path) -> Any:
    return json.loads(read_text(path))


def extract_code_blocks(text: str) -> list[str]:
    return [block.strip() for block in CODE_BLOCK_RE.findall(text)]


INVALID_JSON_BACKSLASH_RE = re.compile(r"\\(?![\"\\/bfnrtu])")


def _loads_json_with_invalid_backslash_repair(candidate: str) -> dict[str, Any]:
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as original_exc:
        repaired = INVALID_JSON_BACKSLASH_RE.sub(r"\\\\", candidate)
        if repaired == candidate:
            raise
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            raise original_exc


def extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return _loads_json_with_invalid_backslash_repair(stripped)

    for block in extract_code_blocks(text):
        try:
            return _loads_json_with_invalid_backslash_repair(block)
        except json.JSONDecodeError:
            continue

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        try:
            return _loads_json_with_invalid_backslash_repair(candidate)
        except json.JSONDecodeError as exc:
            raise ExtractionError(f"Unable to parse JSON payload: {exc}") from exc
    raise ExtractionError("No JSON object found in model output.")


def extract_latex(text: str) -> str:
    for block in extract_code_blocks(text):
        if "\\documentclass" in block or "\\section" in block or "\\begin{document}" in block:
            return block.strip() + "\n"
    stripped = text.strip()
    if stripped:
        return stripped + ("\n" if not stripped.endswith("\n") else "")
    raise ExtractionError("No LaTeX content found in model output.")
