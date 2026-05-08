from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

from .io_utils import read_json
from .pipeline import ContractError
from .session import artifact_path, load_session, runtime_root

def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def _file_sha256(path: str | Path | None) -> str | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return None
    return _sha256_bytes(candidate.read_bytes())

def _sha256_digest(value: str | None) -> str | None:
    if not value:
        return None
    return value.split("sha256:", 1)[1] if value.startswith("sha256:") else value

def _sha256_prefixed(value: str | None) -> str | None:
    digest = _sha256_digest(value)
    return f"sha256:{digest}" if digest else None

def _canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

def _canonical_sha256(payload: Any) -> str:
    return _sha256_bytes(_canonical_json_bytes(payload))

def _packet_sha256(packet: dict[str, Any]) -> str:
    normalized = dict(packet)
    normalized.pop("packet_sha256", None)
    return _canonical_sha256(normalized)

def _artifact_record(role: str, path: str | Path | None, *, required: bool = False) -> dict[str, Any] | None:
    if not path:
        if required:
            raise ContractError(f"required operator review artifact is missing: {role}")
        return None
    candidate = Path(path).resolve()
    if not candidate.exists() or not candidate.is_file():
        if required:
            raise ContractError(f"required operator review artifact is missing: {role}: {candidate}")
        return None
    return {
        "role": role,
        "path": str(candidate),
        "sha256": _file_sha256(candidate),
        "size_bytes": candidate.stat().st_size,
    }

def _safe_packet_artifact_name(role: str, digest: str, source: Path) -> str:
    safe_role = re.sub(r"[^A-Za-z0-9_.-]+", "-", role).strip("-") or "artifact"
    suffix = "".join(source.suffixes[-2:]) if source.suffixes else ".artifact"
    return f"{safe_role}.{digest[:16]}{suffix}"

def _snapshot_operator_packet_artifacts(packet_path: Path, artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Freeze packet-bound artifacts next to the packet before hashing it."""

    snapshot_dir = packet_path.with_suffix(".artifacts")
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    frozen: list[dict[str, Any]] = []
    for artifact in artifacts:
        source = Path(str(artifact.get("path") or "")).resolve()
        digest = str(artifact.get("sha256") or _file_sha256(source) or "")
        if not digest or not source.exists() or not source.is_file():
            frozen.append(dict(artifact))
            continue
        dest = snapshot_dir / _safe_packet_artifact_name(str(artifact.get("role") or "artifact"), digest, source)
        if not dest.exists() or _file_sha256(dest) != digest:
            shutil.copy2(source, dest)
        record = dict(artifact)
        record["original_path"] = str(source)
        record["path"] = str(dest.resolve())
        record["snapshot_path"] = str(dest.resolve())
        record["sha256"] = digest
        record["size_bytes"] = dest.stat().st_size
        frozen.append(record)
    return frozen

def _first_existing(*paths: str | Path | None) -> Path | None:
    for path in paths:
        if not path:
            continue
        candidate = Path(path).resolve()
        if candidate.exists() and candidate.is_file():
            return candidate
    return None

def _latest_human_needed_execution(cwd: str | Path | None) -> Path | None:
    executions = sorted(runtime_root(cwd).glob("qa-loop-execution.iter-*.json"))
    if not executions:
        return None
    latest = executions[-1]
    try:
        payload = read_json(latest)
    except Exception:
        return None
    if isinstance(payload, dict) and payload.get("verdict") == "human_needed":
        return latest
    return None

def _latest_human_needed_operator_feedback_execution(cwd: str | Path | None) -> Path | None:
    path = artifact_path(cwd, "operator_feedback.execution.json")
    if not path.exists() or not path.is_file():
        return None
    try:
        payload = read_json(path)
    except Exception:
        return None
    if isinstance(payload, dict) and payload.get("verdict") == "human_needed":
        return path
    return None

def _execution_payload_opens_candidate_review(
    execution_path: Path,
    payload: dict[str, Any],
    *,
    current_manuscript_sha256: str,
) -> bool:
    """Return true when a qa/operator execution is the active candidate-review gate.

    A semi-automatic qa-loop step can make real progress, restore the canonical
    manuscript, and then stop at `human_needed` so an operator can approve the
    candidate. In that state the current `qa-loop.plan.json` remains `continue`
    for the canonical manuscript, but the latest execution artifact is the
    active human-needed gate. Accept only hash-bound execution artifacts so old
    candidate approvals cannot reopen the operator lane.
    """

    if payload.get("verdict") != "human_needed":
        return False
    approval = payload.get("candidate_approval")
    if not isinstance(approval, dict) or approval.get("status") != "human_needed_candidate_ready":
        return False
    if _normalized_sha(approval.get("base_manuscript_sha256")) != current_manuscript_sha256:
        return False
    if not approval.get("created_at"):
        return False
    source_path_text = str(approval.get("source_execution_path") or "").strip()
    if not source_path_text:
        return False
    try:
        if Path(source_path_text).resolve() != execution_path.resolve():
            return False
    except Exception:
        return False
    if str(approval.get("source_execution_sha256") or "") != _execution_payload_sha256(payload):
        return False
    candidate_path = approval.get("candidate_path")
    candidate_sha = _normalized_sha(approval.get("candidate_sha256"))
    if not candidate_path or not candidate_sha:
        return False
    if _normalized_sha(_file_sha256(candidate_path)) != candidate_sha:
        return False
    progress = payload.get("candidate_progress")
    if isinstance(progress, dict) and progress.get("forward_progress") is not True:
        return False
    return True

def _execution_payload_opens_operator_review(
    execution_path: Path,
    payload: dict[str, Any],
    *,
    current_manuscript_sha256: str,
) -> bool:
    """Return true when the latest QA/operator execution is an active operator stop.

    Candidate approvals are one operator stop shape, but not the only one.  A
    semi-automatic repair can also try a candidate, reject it, restore the
    canonical manuscript, and return `human_needed` because the bounded repair
    lane cannot make safe progress.  In that state the current
    `qa-loop.plan.json` is still `continue` for the canonical manuscript, so
    packet construction must use the hash-bound execution artifact as the
    operator-lane authority instead of requiring the plan itself to be
    terminal.
    """

    if _execution_payload_opens_candidate_review(
        execution_path,
        payload,
        current_manuscript_sha256=current_manuscript_sha256,
    ):
        return True
    if payload.get("verdict") != "human_needed":
        return False
    bound_sha = _artifact_bound_manuscript_sha("qa_loop_execution", payload)
    if bound_sha != current_manuscript_sha256:
        return False
    if payload.get("no_progress_override") is True:
        return True
    handoff = payload.get("candidate_handoff")
    if isinstance(handoff, dict) and str(handoff.get("status") or "").startswith("human_needed_candidate_rejected"):
        return True
    reason = str(payload.get("reason") or "")
    if reason in {"no_supported_executable_handlers"}:
        return True
    return False

def _current_bound_execution_path(path: Path | None, *, role: str, current_manuscript_sha256: str | None) -> Path | None:
    if path is None or not current_manuscript_sha256:
        return path
    try:
        payload = read_json(path)
    except Exception:
        return path
    if not isinstance(payload, dict):
        return path
    bound_sha = _artifact_bound_manuscript_sha(role, payload)
    if bound_sha is not None and bound_sha != current_manuscript_sha256:
        return None
    return path

def _first_current_bound_existing(
    role: str,
    current_manuscript_sha256: str | None,
    *paths: str | Path | None,
) -> Path | None:
    """Return the first existing artifact that is not stale for the current manuscript.

    Operator packets may have multiple candidate locations for the same review
    role. A stale high-priority pointer must not veto a fresher fallback copy;
    otherwise one old session pointer can hide valid current review evidence.
    """

    for path in paths:
        candidate = _first_existing(path)
        if candidate is None:
            continue
        current = _current_bound_execution_path(
            candidate,
            role=role,
            current_manuscript_sha256=current_manuscript_sha256,
        )
        if current is not None:
            return current
    return None

def _operator_review_human_needed_artifacts(cwd: str | Path | None) -> tuple[Path | None, Path | None, Path | None]:
    plan_path = artifact_path(cwd, "qa-loop.plan.json")
    qa_plan_path = plan_path if plan_path.exists() and plan_path.is_file() else None
    qa_execution_path = _latest_human_needed_execution(cwd)
    operator_execution_path = _latest_human_needed_operator_feedback_execution(cwd)
    state = load_session(cwd)
    current_sha = _normalized_sha(_file_sha256(state.artifacts.paper_full_tex))
    if qa_plan_path is not None:
        plan = read_json(qa_plan_path)
        if isinstance(plan, dict) and plan.get("verdict") == "human_needed":
            return (
                qa_plan_path,
                _current_bound_execution_path(
                    qa_execution_path,
                    role="qa_loop_execution",
                    current_manuscript_sha256=current_sha,
                ),
                _current_bound_execution_path(
                    operator_execution_path,
                    role="operator_feedback_execution",
                    current_manuscript_sha256=current_sha,
                ),
            )
    if qa_plan_path is not None and qa_execution_path is not None and current_sha:
        try:
            execution = read_json(qa_execution_path)
        except Exception:
            execution = None
        if isinstance(execution, dict) and _execution_payload_opens_operator_review(
            qa_execution_path,
            execution,
            current_manuscript_sha256=current_sha,
        ):
            return (
                qa_plan_path,
                qa_execution_path,
                _current_bound_execution_path(
                    operator_execution_path,
                    role="operator_feedback_execution",
                    current_manuscript_sha256=current_sha,
                ),
            )
    raise ContractError(
        "operator feedback requires current qa-loop.plan.json verdict=human_needed "
        "or a hash-bound latest qa-loop execution that opens an operator review stop; "
        "stale QA/operator-feedback execution artifacts cannot reopen the operator lane"
    )

def _artifact_by_role(packet: dict[str, Any], role: str) -> dict[str, Any] | None:
    for artifact in packet.get("artifacts") or []:
        if isinstance(artifact, dict) and artifact.get("role") == role:
            return artifact
    return None

def _packet_has_human_needed_context(packet: dict[str, Any]) -> bool:
    for role in ("qa_loop_plan", "qa_loop_execution", "operator_feedback_execution"):
        record = _artifact_by_role(packet, role)
        if not record:
            continue
        try:
            payload = read_json(record["path"])
        except Exception:
            payload = None
        if isinstance(payload, dict) and payload.get("verdict") == "human_needed":
            return True
    return False

def _normalized_sha(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text.split("sha256:", 1)[1] if text.startswith("sha256:") else text

def _artifact_payload(record: dict[str, Any]) -> dict[str, Any] | None:
    try:
        payload = read_json(record["path"])
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None

def _artifact_bound_manuscript_sha(role: str, payload: dict[str, Any]) -> str | None:
    if role in {"citation_support_review", "section_review"}:
        return _normalized_sha(payload.get("manuscript_sha256"))
    if role == "quality_eval":
        return _normalized_sha(payload.get("manuscript_hash"))
    if role == "qa_loop_plan":
        summary = payload.get("quality_eval_summary") if isinstance(payload.get("quality_eval_summary"), dict) else {}
        return _normalized_sha(summary.get("manuscript_hash"))
    if role == "qa_loop_execution":
        progress = payload.get("progress") if isinstance(payload.get("progress"), dict) else {}
        restored_state = payload.get("restored_current_state") if isinstance(payload.get("restored_current_state"), dict) else {}
        restored_progress = restored_state.get("progress") if isinstance(restored_state.get("progress"), dict) else {}
        return _normalized_sha(
            payload.get("manuscript_sha256_before")
            or (payload.get("candidate_approval") or {}).get("base_manuscript_sha256")
            or progress.get("before_manuscript_hash")
            or restored_progress.get("before_manuscript_hash")
        )
    if role == "operator_feedback_execution":
        return _normalized_sha(
            payload.get("manuscript_sha256_before")
            or (payload.get("candidate_approval") or {}).get("base_manuscript_sha256")
            or ((payload.get("candidate_result") or {}).get("candidate_approval") or {}).get("base_manuscript_sha256")
        )
    return None

def _validate_current_operator_plan(
    *,
    cwd: str | Path | None,
    session_id: str,
    current_manuscript_sha256: str,
    allow_operator_review_context: bool = False,
) -> None:
    plan_path = artifact_path(cwd, "qa-loop.plan.json")
    try:
        plan = read_json(plan_path)
    except Exception as exc:
        raise ContractError("operator feedback requires readable current qa-loop.plan.json") from exc
    if not isinstance(plan, dict):
        raise ContractError("operator feedback requires readable current qa-loop.plan.json")
    plan_verdict = plan.get("verdict")
    if allow_operator_review_context:
        if plan_verdict not in {"continue", "human_needed"}:
            raise ContractError(
                "operator feedback operator review stop requires current qa-loop.plan.json verdict=continue or human_needed"
            )
    elif plan_verdict != "human_needed":
        raise ContractError("operator feedback requires current qa-loop.plan.json verdict=human_needed")
    if plan.get("session_id") != session_id:
        raise ContractError("operator feedback current qa-loop.plan.json session_id mismatch")
    bound_sha = _artifact_bound_manuscript_sha("qa_loop_plan", plan)
    if bound_sha is None:
        raise ContractError("operator feedback current qa-loop.plan.json lacks manuscript hash binding")
    if bound_sha != current_manuscript_sha256:
        raise ContractError("operator feedback current qa-loop.plan.json is stale for current manuscript")

def _validate_operator_packet_artifact_bindings(
    *,
    cwd: str | Path | None,
    packet: dict[str, Any],
    current_manuscript_sha256: str,
) -> None:
    state = load_session(cwd)
    if packet.get("session_id") != state.session_id:
        raise ContractError("operator review packet session_id does not match current session")
    current_sha = _file_sha256(state.artifacts.paper_full_tex)
    if current_sha != current_manuscript_sha256:
        raise ContractError("operator review packet manuscript hash is stale for the current manuscript")

    artifacts = packet.get("artifacts") if isinstance(packet.get("artifacts"), list) else []
    records_by_role = {str(record.get("role")): record for record in artifacts if isinstance(record, dict)}
    qa_execution_payload = None
    qa_execution_record = records_by_role.get("qa_loop_execution")
    if qa_execution_record:
        qa_execution_payload = _artifact_payload(qa_execution_record)
    has_operator_review_context = (
        isinstance(qa_execution_payload, dict)
        and _execution_payload_opens_operator_review(
            Path(str(qa_execution_record.get("original_path") or qa_execution_record.get("path"))),
            qa_execution_payload,
            current_manuscript_sha256=current_manuscript_sha256,
        )
    )
    _validate_current_operator_plan(
        cwd=cwd,
        session_id=state.session_id,
        current_manuscript_sha256=current_manuscript_sha256,
        allow_operator_review_context=has_operator_review_context,
    )
    plan_record = records_by_role.get("qa_loop_plan")
    if not plan_record:
        raise ContractError("operator review packet requires a current qa_loop_plan artifact")
    plan_payload = _artifact_payload(plan_record)
    if not isinstance(plan_payload, dict):
        raise ContractError("operator review packet requires readable qa_loop_plan artifact")
    if has_operator_review_context:
        if plan_payload.get("verdict") not in {"continue", "human_needed"}:
            raise ContractError("operator review packet operator stop requires qa_loop_plan verdict=continue or human_needed")
    elif plan_payload.get("verdict") != "human_needed":
        raise ContractError("operator review packet requires qa_loop_plan verdict=human_needed")

    for role in {
        "quality_eval",
        "qa_loop_plan",
        "qa_loop_execution",
        "operator_feedback_execution",
        "citation_support_review",
        "section_review",
    }:
        record = records_by_role.get(role)
        if not record:
            continue
        payload = _artifact_payload(record)
        if payload is None:
            raise ContractError(f"operator review packet artifact is unreadable: {role}")
        bound_sha = _artifact_bound_manuscript_sha(role, payload)
        if bound_sha is None:
            if role == "qa_loop_plan":
                raise ContractError(f"operator review packet artifact lacks manuscript hash binding: {role}")
            continue
        if (
            role in {"qa_loop_execution", "operator_feedback_execution"}
            and not has_operator_review_context
            and isinstance(plan_payload, dict)
            and plan_payload.get("verdict") == "human_needed"
            and bound_sha != current_manuscript_sha256
        ):
            continue
        if bound_sha != current_manuscript_sha256:
            raise ContractError(f"operator review packet artifact is stale for current manuscript: {role}")

def _execution_payload_sha256(execution: dict[str, Any]) -> str:
    payload_for_hash = json.loads(json.dumps(execution, sort_keys=True))
    approval = payload_for_hash.get("candidate_approval")
    if isinstance(approval, dict):
        approval.pop("source_execution_sha256", None)
    return "sha256:" + hashlib.sha256(
        json.dumps(payload_for_hash, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
