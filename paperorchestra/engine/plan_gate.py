from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from paperorchestra.core.errors import ContractError
from paperorchestra.core.session_paths import CURRENT_FILE, ROOT_DIRNAME, project_root

_APPROVAL_PATTERNS = (
    re.compile(r"<!--\s*paperorchestra:plan-approved\s*-->", re.IGNORECASE),
    re.compile(r"(?m)^\s*(?:plan_status|status)\s*:\s*approved\s*$", re.IGNORECASE),
    re.compile(r"(?m)^\s*(?:approved|author_approved)\s*:\s*true\s*$", re.IGNORECASE),
)

_PLAN_FILENAME = "paper-plan.md"
_NEXT_ACTION = (
    "Run `$paperorchestra-plan`, review `paper-plan.md`, then mark author approval "
    "with `<!-- paperorchestra:plan-approved -->`. Use `bypass_plan_gate` only for explicit legacy runs."
)


@dataclass(frozen=True)
class PlanGateResult:
    allowed: bool
    reason: str
    message: str
    plan_path: str | None = None
    next_action: str = _NEXT_ACTION
    bypassed: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "message": self.message,
            "plan_path": self.plan_path,
            "next_action": self.next_action,
            "bypassed": self.bypassed,
        }

    def to_blocked_payload(self) -> dict[str, object]:
        return {
            "status": "blocked",
            "reason": self.reason,
            "message": self.message,
            "next_action": self.next_action,
            "plan_gate": self.to_dict(),
        }


def candidate_plan_paths(cwd: str | Path | None) -> list[Path]:
    root = project_root(cwd)
    runtime = root / ROOT_DIRNAME
    paths = [root / _PLAN_FILENAME, runtime / _PLAN_FILENAME]

    current_session = _read_current_session_id(runtime)
    if current_session:
        run_root = runtime / "runs" / current_session
        paths.extend([run_root / "artifacts" / _PLAN_FILENAME, run_root / _PLAN_FILENAME])

    return _dedupe(paths)


def check_plan_gate(cwd: str | Path | None, *, bypass: bool = False) -> PlanGateResult:
    existing = [path for path in candidate_plan_paths(cwd) if path.exists()]
    approved = next((path for path in existing if is_plan_approved(path)), None)

    if bypass:
        return PlanGateResult(
            allowed=True,
            reason="paper_plan_gate_bypassed",
            message="Paper plan approval gate bypassed by explicit caller request.",
            plan_path=str(approved or existing[0]) if existing else None,
            bypassed=True,
        )

    if approved is not None:
        return PlanGateResult(
            allowed=True,
            reason="paper_plan_approved",
            message="Paper plan is present and author-approved.",
            plan_path=str(approved),
        )

    if existing:
        return PlanGateResult(
            allowed=False,
            reason="paper_plan_unapproved",
            message=(
                f"Found `{existing[0]}` but it is not author-approved. "
                "Draft-generating actions require an approved paper-plan.md first."
            ),
            plan_path=str(existing[0]),
        )

    return PlanGateResult(
        allowed=False,
        reason="paper_plan_missing",
        message="Draft-generating actions require an author-approved paper-plan.md first.",
    )


def approved_plan_path(cwd: str | Path | None) -> Path | None:
    """Return the author-approved plan path, if one exists.

    This is intentionally stricter than "first paper-plan.md on disk":
    unapproved plans can exist during intake/iteration and must not become
    hidden drafting context.
    """
    return next((path for path in candidate_plan_paths(cwd) if path.exists() and is_plan_approved(path)), None)


def ensure_approved_plan(cwd: str | Path | None, *, bypass: bool = False) -> PlanGateResult:
    result = check_plan_gate(cwd, bypass=bypass)
    if not result.allowed:
        raise ContractError(f"{result.message} Next action: {result.next_action}")
    return result


def is_plan_approved(path: str | Path) -> bool:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return False
    return any(pattern.search(text) for pattern in _APPROVAL_PATTERNS)


def _read_current_session_id(runtime: Path) -> str | None:
    current_file = runtime / CURRENT_FILE
    if not current_file.exists():
        return None
    try:
        return current_file.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _dedupe(paths: Iterable[Path]) -> list[Path]:
    seen: set[Path] = set()
    result: list[Path] = []
    for path in paths:
        resolved = path.resolve(strict=False)
        if resolved in seen:
            continue
        seen.add(resolved)
        result.append(path)
    return result


__all__ = [
    "PlanGateResult",
    "approved_plan_path",
    "candidate_plan_paths",
    "check_plan_gate",
    "ensure_approved_plan",
    "is_plan_approved",
]
