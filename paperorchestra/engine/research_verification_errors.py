from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import write_json
from paperorchestra.core.session import artifact_path


def _record_verification_errors(
    cwd: str | Path | None,
    state: Any,
    errors: list[dict[str, Any]],
    *,
    mode: str,
    on_error: str,
) -> Path | None:
    if not errors:
        return None
    path = artifact_path(cwd, "verification_errors.json")
    write_json(
        path,
        {
            "mode": mode,
            "on_error": on_error,
            "error_count": len(errors),
            "errors": errors,
            "recovery_hints": [
                "Set SEMANTIC_SCHOLAR_API_KEY for more reliable live verification.",
                "Retry `paperorchestra run --provider shell --discovery-mode search-grounded` to keep any candidates that verify successfully.",
                "Use `paperorchestra run --provider mock` only for demos or offline dry runs.",
            ],
        },
    )
    state.artifacts.latest_verification_errors_json = str(path)
    state.notes.append(f"Recorded {len(errors)} live verification error(s): {path.name}")
    return path
