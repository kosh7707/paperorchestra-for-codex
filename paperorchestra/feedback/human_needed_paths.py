from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.core.session import project_root, run_dir, runtime_root


def _project_root_for_path(cwd: str | Path | None) -> Path:
    return project_root(cwd).resolve()


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _private_answer_path(
    cwd: str | Path | None,
    session_id: str,
    answer_id: str,
    output_answer: str | Path | None,
    *,
    redacted_answer_only: bool,
) -> Path | None:
    if redacted_answer_only:
        return None
    private_root = runtime_root(cwd) / "private" / "human-needed" / session_id
    if output_answer is None:
        return private_root / f"{answer_id}.json"
    candidate = Path(output_answer).resolve()
    repo = _project_root_for_path(cwd)
    allowed_private = private_root.resolve()
    if _is_within(candidate, allowed_private):
        return candidate
    if not _is_within(candidate, repo):
        return candidate
    raise ContractError("private answer output must be under .paper-orchestra/private/human-needed, outside the project root, or omitted")


def _public_result_path(cwd: str | Path | None, path: str | Path) -> str | None:
    candidate = Path(path).resolve()
    try:
        candidate.relative_to(run_dir(cwd).resolve())
        return str(candidate)
    except ValueError:
        return None


def _attach_public_path_or_label(result: dict[str, Any], cwd: str | Path | None, key: str, path: str | Path) -> None:
    public_path = _public_result_path(cwd, path)
    if public_path:
        result[key] = public_path
    else:
        result[f"{key}_label"] = "redacted_external_or_private_path"
