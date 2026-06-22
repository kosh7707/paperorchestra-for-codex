from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from paperorchestra.core.errors import ContractError
from paperorchestra.core.session_paths import CURRENT_FILE, ROOT_DIRNAME, project_root

PLAN_CONTRACT_HASH_VERSION = "1"
PLAN_APPROVAL_SCHEMA_VERSION = "paperorchestra/plan-approval/1"
_HASHED_APPROVAL_PATTERN = re.compile(
    r"<!--\s*paperorchestra:plan-approved\s+revision=(?P<revision>\d+)\s+"
    r"(?:(?:hash-v|hash_version)=(?P<hash_version>\d+)\s+)?contract-sha256=(?P<hash>[a-f0-9]{64})\s*-->",
    re.IGNORECASE,
)
_ANY_APPROVAL_MARKER_PATTERN = re.compile(r"<!--\s*paperorchestra:plan-approved(?:\s+[^>]*)?\s*-->", re.IGNORECASE)
_LEGACY_MARKER_PATTERN = re.compile(r"<!--\s*paperorchestra:plan-approved\s*-->", re.IGNORECASE)
_LEGACY_YAML_PATTERNS = (
    re.compile(r"(?m)^\s*(?:plan_status|status)\s*:\s*approved\s*$", re.IGNORECASE),
    re.compile(r"(?m)^\s*(?:approved|author_approved)\s*:\s*true\s*$", re.IGNORECASE),
)
_V3_SCHEMA_PATTERN = re.compile(r"(?m)^\s*schema\s*:\s*paperorchestra/paper-plan/(?:v?3)\s*$", re.IGNORECASE)
_IGNORED_CONTRACT_KEYS = {
    "generated_at",
    "updated_at",
    "output_workspace",
    "run_id",
    "current_session_id",
}
_UNORDERED_FRONTMATTER_MAP_KEYS = {
    "material_snapshot",
    "source_intake",
}

_PLAN_FILENAME = "paper-plan.md"
_NEXT_ACTION = (
    "Run `$paperorchestra-plan`, review `paper-plan.md`, then approve it with `paperorchestra approve-plan`. "
    "Legacy unhashed approvals are transitional only. Use `bypass_plan_gate` only for explicit legacy runs."
)


@dataclass(frozen=True)
class PlanGateResult:
    allowed: bool
    reason: str
    message: str
    plan_path: str | None = None
    next_action: str = _NEXT_ACTION
    bypassed: bool = False
    approval_state: str | None = None
    approval_revision: int | None = None
    approval_hash_version: str | None = None
    contract_sha256: str | None = None
    approval_record_path: str | None = None
    warning: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "message": self.message,
            "plan_path": self.plan_path,
            "next_action": self.next_action,
            "bypassed": self.bypassed,
            "approval_state": self.approval_state,
            "approval_revision": self.approval_revision,
            "approval_hash_version": self.approval_hash_version,
            "contract_sha256": self.contract_sha256,
            "approval_record_path": self.approval_record_path,
            "warning": self.warning,
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
    approval_by_path = {path: plan_approval_info(path) for path in existing}
    approved = next((path for path, approval in approval_by_path.items() if approval.allowed), None)

    if bypass:
        approval = approval_by_path.get(approved or existing[0]) if existing else None
        return PlanGateResult(
            allowed=True,
            reason="paper_plan_gate_bypassed",
            message="Paper plan approval gate bypassed by explicit caller request.",
            plan_path=str(approved or existing[0]) if existing else None,
            bypassed=True,
            approval_state=approval.state if approval else None,
            approval_revision=approval.revision if approval else None,
            approval_hash_version=approval.hash_version if approval else None,
            contract_sha256=approval.actual_hash if approval else None,
            approval_record_path=approval.approval_record_path if approval else None,
            warning=approval.warning if approval else None,
        )

    if approved is not None:
        approval = approval_by_path[approved]
        reason = (
            "paper_plan_approved"
            if approval.state == "approved_sidecar"
            else "paper_plan_approved_hashed"
            if approval.state == "approved_hashed"
            else "legacy_unhashed_approval"
        )
        warning = approval.warning
        message = "Paper plan is present and author-approved."
        if warning:
            message += f" Warning: {warning}"
        return PlanGateResult(
            allowed=True,
            reason=reason,
            message=message,
            plan_path=str(approved),
            approval_state=approval.state,
            approval_revision=approval.revision,
            approval_hash_version=approval.hash_version,
            contract_sha256=approval.actual_hash,
            approval_record_path=approval.approval_record_path,
            warning=warning,
        )

    if existing:
        first = existing[0]
        approval = approval_by_path[first]
        reason = approval.reason or "paper_plan_unapproved"
        message = approval.message or (
            f"Found `{first}` but it is not author-approved. "
            "Draft-generating actions require an approved paper-plan.md first."
        )
        return PlanGateResult(
            allowed=False,
            reason=reason,
            message=message,
            plan_path=str(first),
            approval_state=approval.state,
            approval_revision=approval.revision,
            approval_hash_version=approval.hash_version,
            contract_sha256=approval.actual_hash,
            approval_record_path=approval.approval_record_path,
            warning=approval.warning,
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
    return plan_approval_info(path).allowed


@dataclass(frozen=True)
class PlanApprovalInfo:
    allowed: bool
    state: str
    actual_hash: str | None = None
    expected_hash: str | None = None
    revision: int | None = None
    hash_version: str | None = None
    approval_record_path: str | None = None
    reason: str | None = None
    message: str | None = None
    warning: str | None = None


def plan_approval_info(path: str | Path) -> PlanApprovalInfo:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return PlanApprovalInfo(
            allowed=False,
            state="missing",
            reason="paper_plan_missing",
            message="Paper plan could not be read.",
        )

    actual_hash = compute_plan_contract_sha256(text)
    v3 = _is_v3_plan(text)
    sidecar = _read_plan_approval_record(path)
    if sidecar is not None:
        sidecar_info = _approval_info_from_sidecar(path=Path(path), record=sidecar, actual_hash=actual_hash)
        if sidecar_info is not None:
            return sidecar_info

    hashed = _HASHED_APPROVAL_PATTERN.search(text)
    any_marker = _ANY_APPROVAL_MARKER_PATTERN.search(text)

    if hashed:
        expected_hash = hashed.group("hash").lower()
        revision = int(hashed.group("revision"))
        hash_version = hashed.group("hash_version") or PLAN_CONTRACT_HASH_VERSION
        if hash_version != PLAN_CONTRACT_HASH_VERSION:
            return PlanApprovalInfo(
                allowed=False,
                state="unsupported_hash_version",
                actual_hash=actual_hash,
                expected_hash=expected_hash,
                revision=revision,
                hash_version=hash_version,
            reason="paper_plan_unsupported_hash_version",
            message=(
                "Found a paper-plan approval marker with an unsupported fingerprint schema. "
                "Review the plan and run `paperorchestra approve-plan`."
            ),
        )
        if expected_hash == actual_hash:
            return PlanApprovalInfo(
                allowed=True,
                state="approved_hashed",
                actual_hash=actual_hash,
                expected_hash=expected_hash,
                revision=revision,
                hash_version=hash_version,
                approval_record_path=None,
            )
        return PlanApprovalInfo(
            allowed=False,
            state="stale_hashed",
            actual_hash=actual_hash,
            expected_hash=expected_hash,
            revision=revision,
            hash_version=hash_version,
            reason="paper_plan_stale_approval",
            message=(
                "Found a legacy in-text paper-plan approval marker, but the approved contract no longer matches. "
                "Review the changed paper-plan.md and run `paperorchestra approve-plan`."
            ),
        )

    if v3 and any_marker:
        return PlanApprovalInfo(
            allowed=False,
            state="approval_record_missing",
            actual_hash=actual_hash,
            reason="paper_plan_approval_record_missing",
            message=(
                "Found a v3 paper-plan approval marker, but the hidden approval record is missing or stale. "
                "Review the plan and run `paperorchestra approve-plan`."
            ),
        )

    legacy = _LEGACY_MARKER_PATTERN.search(text) or (not v3 and any(pattern.search(text) for pattern in _LEGACY_YAML_PATTERNS))
    if legacy:
        return PlanApprovalInfo(
            allowed=True,
            state="legacy_unhashed_approval",
            actual_hash=actual_hash,
            reason="legacy_unhashed_approval",
            warning="Legacy paper-plan approval accepted for transition; prefer `paperorchestra approve-plan` before finalization.",
        )

    return PlanApprovalInfo(
        allowed=False,
        state="unapproved",
        actual_hash=actual_hash,
        reason="paper_plan_unapproved",
        message=(
            f"Found `{path}` but it is not author-approved. "
            "Draft-generating actions require an approved paper-plan.md first."
        ),
    )


def compute_plan_contract_sha256(text_or_path: str | Path) -> str:
    text = _read_text_or_value(text_or_path)
    normalized = canonical_plan_contract_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def approve_plan(
    cwd: str | Path | None,
    *,
    plan_path: str | Path | None = None,
    revision: int | None = None,
    approved_by: str = "author",
) -> dict[str, Any]:
    path = _resolve_plan_path_for_approval(cwd, plan_path)
    text = path.read_text(encoding="utf-8")
    contract_hash = compute_plan_contract_sha256(text)
    record = {
        "schema_version": PLAN_APPROVAL_SCHEMA_VERSION,
        "plan_path": str(path.resolve(strict=False)),
        "revision": revision if revision is not None else _plan_revision(text),
        "contract_hash_version": PLAN_CONTRACT_HASH_VERSION,
        "contract_sha256": contract_hash,
        "approved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "approved_by": approved_by,
        "approval_source": "paperorchestra approve-plan",
    }
    sidecar = plan_approval_record_path(path)
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"status": "approved", "plan_path": str(path), "approval_record_path": str(sidecar), **record}


def plan_approval_record_path(plan_path: str | Path) -> Path:
    path = Path(plan_path).resolve(strict=False)
    root = _project_root_for_plan_path(path)
    key = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:12]
    return root / ROOT_DIRNAME / "approvals" / f"{path.stem}-{key}.approval.json"


def _resolve_plan_path_for_approval(cwd: str | Path | None, plan_path: str | Path | None) -> Path:
    if plan_path is not None:
        path = Path(plan_path).expanduser().resolve(strict=False)
        if not path.exists():
            raise FileNotFoundError(f"paper-plan.md not found: {path}")
        return path
    for path in candidate_plan_paths(cwd):
        if path.exists():
            return path.resolve(strict=False)
    raise FileNotFoundError("No paper-plan.md found. Run `$paperorchestra-plan` first.")


def _plan_revision(text: str) -> int | None:
    match = re.search(r"(?m)^\s*revision\s*:\s*(\d+)\s*$", text)
    return int(match.group(1)) if match else None


def _read_plan_approval_record(plan_path: str | Path) -> dict[str, Any] | None:
    sidecar = plan_approval_record_path(plan_path)
    if not sidecar.exists():
        return None
    try:
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "schema_version": PLAN_APPROVAL_SCHEMA_VERSION,
            "invalid": True,
            "approval_record_path": str(sidecar),
        }
    if isinstance(payload, dict):
        payload["approval_record_path"] = str(sidecar)
        return payload
    return {"schema_version": PLAN_APPROVAL_SCHEMA_VERSION, "invalid": True, "approval_record_path": str(sidecar)}


def _approval_info_from_sidecar(path: Path, record: dict[str, Any], actual_hash: str) -> PlanApprovalInfo | None:
    sidecar_path = str(record.get("approval_record_path") or plan_approval_record_path(path))
    if record.get("invalid"):
        return PlanApprovalInfo(
            allowed=False,
            state="approval_record_invalid",
            actual_hash=actual_hash,
            approval_record_path=sidecar_path,
            reason="paper_plan_approval_record_invalid",
            message="The hidden paper-plan approval record is unreadable. Review the plan and run `paperorchestra approve-plan`.",
        )
    if record.get("schema_version") != PLAN_APPROVAL_SCHEMA_VERSION:
        return None
    hash_version = str(record.get("contract_hash_version") or "")
    expected_hash = str(record.get("contract_sha256") or "").lower()
    revision = record.get("revision")
    revision = int(revision) if isinstance(revision, int) or (isinstance(revision, str) and revision.isdigit()) else None
    if hash_version != PLAN_CONTRACT_HASH_VERSION:
        return PlanApprovalInfo(
            allowed=False,
            state="unsupported_hash_version",
            actual_hash=actual_hash,
            expected_hash=expected_hash or None,
            revision=revision,
            hash_version=hash_version or None,
            approval_record_path=sidecar_path,
            reason="paper_plan_unsupported_hash_version",
            message=(
                "Found a paper-plan approval record with an unsupported fingerprint schema. "
                "Review the plan and run `paperorchestra approve-plan`."
            ),
        )
    if expected_hash == actual_hash:
        return PlanApprovalInfo(
            allowed=True,
            state="approved_sidecar",
            actual_hash=actual_hash,
            expected_hash=expected_hash,
            revision=revision,
            hash_version=hash_version,
            approval_record_path=sidecar_path,
        )
    return PlanApprovalInfo(
        allowed=False,
        state="stale_sidecar",
        actual_hash=actual_hash,
        expected_hash=expected_hash or None,
        revision=revision,
        hash_version=hash_version,
        approval_record_path=sidecar_path,
        reason="paper_plan_stale_approval",
        message=(
            "The hidden paper-plan approval record no longer matches the plan. "
            "Review the changed paper-plan.md and run `paperorchestra approve-plan` again."
        ),
    )


def _project_root_for_plan_path(path: Path) -> Path:
    for parent in [path.parent, *path.parents]:
        if parent.name == ROOT_DIRNAME:
            return parent.parent
    return path.parent


def canonical_plan_contract_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _ANY_APPROVAL_MARKER_PATTERN.sub("", text)
    lines = text.split("\n")
    lines = _normalize_frontmatter(lines)
    normalized: list[str] = []
    for line in lines:
        stripped = line.rstrip()
        if _is_ignored_contract_field(stripped):
            continue
        if _is_markdown_table_line(stripped):
            stripped = _normalize_table_row(stripped)
        normalized.append(stripped)
    return "\n".join(normalized).strip() + "\n"


def _read_text_or_value(text_or_path: str | Path) -> str:
    if isinstance(text_or_path, Path):
        return text_or_path.read_text(encoding="utf-8")
    if isinstance(text_or_path, str):
        candidate = Path(text_or_path)
        if "\n" not in text_or_path and candidate.exists():
            return candidate.read_text(encoding="utf-8")
        return text_or_path
    raise TypeError(f"Unsupported plan contract input: {type(text_or_path)!r}")


def _is_v3_plan(text: str) -> bool:
    return bool(_V3_SCHEMA_PATTERN.search(text))


def _is_ignored_contract_field(line: str) -> bool:
    match = re.match(r"^\s*-?\s*([A-Za-z_][\w-]*)\s*:", line)
    if not match:
        return False
    key = match.group(1).replace("-", "_").lower()
    return key in _IGNORED_CONTRACT_KEYS


def _is_markdown_table_line(line: str) -> bool:
    return "|" in line and line.lstrip().startswith("|") and line.rstrip().endswith("|")


def _normalize_table_row(line: str) -> str:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    return "| " + " | ".join(cells) + " |"


def _normalize_frontmatter(lines: list[str]) -> list[str]:
    if not lines or lines[0].strip() != "---":
        return lines
    try:
        end = next(index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration:
        return lines
    frontmatter = lines[1:end]
    rest = lines[end + 1 :]
    sortable_scalars: list[str] = []
    preserved_blocks: list[list[str]] = []
    for block in _frontmatter_blocks(frontmatter):
        if not block:
            continue
        key = _frontmatter_key(block[0])
        if key and key in _IGNORED_CONTRACT_KEYS:
            continue
        normalized = [line.rstrip() for line in block]
        if key in _UNORDERED_FRONTMATTER_MAP_KEYS:
            normalized = _normalize_unordered_frontmatter_map(normalized)
        if len(normalized) == 1 and re.match(r"^\s*[A-Za-z_][\w-]*\s*:\s*[^#]*$", normalized[0]):
            sortable_scalars.append(normalized[0].strip())
        else:
            preserved_blocks.append(normalized)
    return ["---", *sorted(sortable_scalars), *[line for block in preserved_blocks for line in block], "---", *rest]


def _frontmatter_blocks(lines: list[str]) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if _frontmatter_key(line) and current:
            blocks.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append(current)
    return blocks


def _frontmatter_key(line: str) -> str | None:
    match = re.match(r"^([A-Za-z_][\w-]*)\s*:", line)
    if not match:
        return None
    return match.group(1).replace("-", "_").lower()


def _normalize_unordered_frontmatter_map(block: list[str]) -> list[str]:
    if len(block) <= 2:
        return block
    header, children = block[0], block[1:]
    child_blocks = _indented_child_blocks(children)
    return [header, *[line for child in sorted(child_blocks, key=lambda item: item[0].strip().lower()) for line in child]]


def _indented_child_blocks(lines: list[str]) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if re.match(r"^\s+[A-Za-z_][\w-]*\s*:", line) and current:
            blocks.append(current)
            current = [line.rstrip()]
        else:
            current.append(line.rstrip())
    if current:
        blocks.append(current)
    return blocks


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
    "PLAN_CONTRACT_HASH_VERSION",
    "PlanApprovalInfo",
    "PlanGateResult",
    "approve_plan",
    "approved_plan_path",
    "candidate_plan_paths",
    "check_plan_gate",
    "compute_plan_contract_sha256",
    "ensure_approved_plan",
    "is_plan_approved",
    "plan_approval_record_path",
    "plan_approval_info",
]
