from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

from paperorchestra.core.io import read_json, write_json
from paperorchestra.core.models import utc_now_iso
from paperorchestra.feedback.operator_feedback import (
    apply_operator_feedback,
    build_operator_review_packet,
    import_operator_feedback,
    _read_packet,
)
from paperorchestra.feedback.normalization import (
    actionable_candidate_approval_role,
    normalize_operator_feedback_draft,
)
from paperorchestra.feedback.packets import _artifact_by_role, _file_sha256, _validate_operator_packet_artifact_bindings
from paperorchestra.core.errors import ContractError
from paperorchestra.runtime.providers import BaseProvider, MockProvider
from paperorchestra.core.session import artifact_path, load_session, project_root, run_dir, runtime_root

HUMAN_NEEDED_ANSWER_SCHEMA_VERSION = "human-needed-answer/1"
HUMAN_NEEDED_PUBLIC_SCHEMA_VERSION = "human-needed-answer-public/1"
HUMAN_NEEDED_METADATA_SCHEMA_VERSION = "human-needed-answer-metadata/1"

HUMAN_NEEDED_DECISION_KINDS = {
    "approve_existing_candidate",
    "generate_new_operator_candidate",
    "reject_candidate_with_reason",
}


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def _packet_file_sha256_after_canonical_validation(packet_path: Path, packet: dict[str, Any]) -> str:
    """Return the packet file hash after rejecting non-canonical packet bytes.

    The packet's embedded packet_sha256 protects semantic JSON contents.  The
    human-needed answer also binds to the exact file handed to the operator, so
    whitespace-only post-generation edits must not silently pass as the reviewed
    artifact.
    """

    text = packet_path.read_text(encoding="utf-8")
    if text != _canonical_json(packet):
        raise ContractError("operator review packet file hash does not match canonical contents")
    return _sha256_file(packet_path)


def _artifact_source(packet: dict[str, Any], role: str | None) -> dict[str, str] | None:
    if not role:
        return None
    record = _artifact_by_role(packet, role)
    if not record:
        return None
    return {
        "role": str(record.get("role") or role),
        "sha256": str(record.get("sha256") or ""),
    }


def _load_artifact_payload(packet: dict[str, Any], role: str) -> dict[str, Any] | None:
    record = _artifact_by_role(packet, role)
    if not record:
        return None
    try:
        payload = read_json(record["path"])
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _human_needed_actions(packet: dict[str, Any]) -> list[dict[str, Any]]:
    plan = _load_artifact_payload(packet, "qa_loop_plan")
    if not isinstance(plan, dict):
        return []
    result: list[dict[str, Any]] = []
    for action in plan.get("repair_actions") or []:
        if isinstance(action, dict) and str(action.get("automation") or "") == "human_needed":
            result.append(action)
    return result


def _classify_action(action: dict[str, Any] | None, *, candidate_role: str | None = None) -> str:
    if candidate_role:
        return "candidate_approval"
    text = " ".join(
        str((action or {}).get(key) or "")
        for key in ("id", "action_id", "code", "target", "reason", "suggested_action")
    ).lower()
    if any(token in text for token in ("citation", "reference", "bibliography", "claim")):
        return "citation_author_judgment"
    if any(token in text for token in ("figure", "plot", "caption", "asset")):
        return "figure_grounding_decision"
    if any(token in text for token in ("environment", "dependency", "compile", "sandbox")):
        return "environment_dependency"
    if "reviewer" in text or "independent" in text:
        return "reviewer_independence"
    if any(token in text for token in ("no_progress", "budget", "retry", "stuck")):
        return "no_progress_escalation"
    if _action_id(action) or (action or {}).get("code"):
        return "general_operator_feedback"
    return "unsupported_handler"


def _explicit_reject(answer: str) -> bool:
    lowered = answer.lower()
    return any(
        token in lowered
        for token in (
            "reject",
            "do not",
            "don't",
            "rollback",
            "거절",
            "반려",
            "하지마",
            "하지 마",
            "승인하지",
            "approve하지",
        )
    )


def _explicit_approve(answer: str) -> bool:
    lowered = answer.lower()
    # Candidate promotion is a stronger act than "continue the loop".  Avoid
    # broad conversational/proceed tokens such as "좋아", "반영", or "진행";
    # those should generate a new bounded operator candidate unless the caller
    # supplies --intent approve_existing_candidate.
    approval_patterns = (
        r"\bapprove_existing_candidate\b",
        r"\bapprove\s+(?:the\s+)?(?:existing\s+|ready\s+)?candidate\b",
        r"\bpromote\s+(?:the\s+)?(?:existing\s+|ready\s+)?candidate\b",
        r"\baccept\s+(?:the\s+)?(?:existing\s+|ready\s+)?candidate\b",
        r"후보(?:를)?\s*승인",
        r"후보(?:를)?\s*채택",
        r"candidate(?:를)?\s*승인",
    )
    return any(re.search(pattern, lowered) for pattern in approval_patterns)


def _resolve_decision_kind(answer: str, intent: str | None, *, candidate_role: str | None) -> str:
    if _explicit_reject(answer):
        return "reject_candidate_with_reason"
    if intent:
        if intent not in HUMAN_NEEDED_DECISION_KINDS:
            raise ContractError(f"unsupported human_needed intent: {intent}")
        if intent == "approve_existing_candidate" and not candidate_role:
            raise ContractError("approve_existing_candidate requires an actionable candidate approval artifact")
        return intent
    if candidate_role and _explicit_approve(answer):
        return "approve_existing_candidate"
    return "generate_new_operator_candidate"


def _select_action(actions: list[dict[str, Any]], action_id: str | None, *, candidate_role: str | None) -> dict[str, Any] | None:
    if action_id:
        matches = [action for action in actions if _action_id(action) == action_id]
        if len(matches) != 1:
            raise ContractError(f"human_needed action_id not found or ambiguous: {action_id}")
        return matches[0]
    if len(actions) > 1 and not candidate_role:
        raise ContractError("multiple human_needed actions require --action-id")
    if len(actions) == 1:
        return actions[0]
    return None


def _action_id(action: dict[str, Any] | None) -> str:
    if not isinstance(action, dict):
        return ""
    return str(action.get("id") or action.get("action_id") or "").strip()


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


def _draft_issue_for_action(
    *,
    action: dict[str, Any] | None,
    handoff_type: str,
    decision_kind: str,
    candidate_role: str | None,
) -> dict[str, Any]:
    if candidate_role and decision_kind == "approve_existing_candidate":
        return {
            "source_artifact_role": candidate_role,
            "source_item_key": "candidate_approval",
            "target_section": "Whole manuscript",
            "severity": "major",
            "rationale": "The operator explicitly approved a hash-bound forward-progress candidate exposed by the human_needed packet.",
            "suggested_action": (
                "Import this as approve_existing_candidate author feedback. "
                "apply_operator_feedback must re-read the packet-bound candidate_approval, verify candidate/base/source hashes "
                "and forward-progress evidence, then promote only after the operator-feedback hard gate passes."
            ),
            "authority_class": "author_feedback",
            "owner_category": "author",
        }
    source_key = str((action or {}).get("code") or _action_id(action) or f"human_needed:{handoff_type}")
    target = str((action or {}).get("target") or "Whole manuscript")
    reason = str((action or {}).get("reason") or "The QA loop reached human_needed and requires bounded operator judgment.")
    if decision_kind == "reject_candidate_with_reason":
        suggested = "Reject the currently exposed candidate or unsafe direction; keep the canonical manuscript unchanged and request a safer repair plan."
    else:
        suggested = "Generate a bounded operator-feedback candidate that addresses this human_needed handoff using only packet-grounded manuscript evidence."
    return {
        "source_artifact_role": "qa_loop_plan",
        "source_item_key": source_key,
        "target_section": target,
        "severity": "major",
        "rationale": reason,
        "suggested_action": suggested,
        "authority_class": "author_feedback",
        "owner_category": "author",
    }


def _metadata_without_targets(
    *,
    packet: dict[str, Any],
    packet_file_sha256: str,
    answer_sha256: str,
    private_answer_artifact_sha256: str | None,
    decision_kind: str,
    handoff_type: str,
    action: dict[str, Any] | None,
    candidate_role: str | None,
) -> dict[str, Any]:
    selected = _artifact_source(packet, candidate_role or "qa_loop_plan")
    return {
        "schema_version": HUMAN_NEEDED_METADATA_SCHEMA_VERSION,
        "session_id": packet.get("session_id"),
        "packet_sha256": packet.get("packet_sha256"),
        "packet_file_sha256": packet_file_sha256,
        "manuscript_sha256": packet.get("manuscript_sha256"),
        "answer_sha256": answer_sha256,
        "private_answer_artifact_sha256": private_answer_artifact_sha256,
        "decision_kind": decision_kind,
        "handoff_type": handoff_type,
        "target_action_id": _action_id(action) or None,
        "selected_handoff_source": selected,
        "answer": "redacted",
    }


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


def record_human_needed_answer(
    cwd: str | Path | None,
    answer: str,
    *,
    packet_path: str | Path | None = None,
    review_scope: str | None = None,
    intent: str | None = None,
    action_id: str | None = None,
    output_answer: str | Path | None = None,
    output_feedback: str | Path | None = None,
    redacted_answer_only: bool = False,
    apply: bool = False,
    imported_feedback_output: str | Path | None = None,
    provider: BaseProvider | None = None,
    max_supervised_iterations: int = 1,
    require_compile: bool = False,
    quality_mode: str = "claim_safe",
    max_iterations: int = 10,
    require_live_verification: bool = False,
    accept_mixed_provenance: bool = False,
    runtime_mode: str = "compatibility",
    citation_evidence_mode: str = "web",
    citation_provider_name: str | None = None,
    citation_provider_command: str | None = None,
) -> dict[str, Any]:
    answer = str(answer or "")
    if not answer.strip():
        raise ContractError("human_needed answer must not be empty")

    if packet_path is None:
        packet_path_obj, packet = build_operator_review_packet(cwd, review_scope=review_scope)
    else:
        packet_path_obj = Path(packet_path).resolve()
        packet = _read_packet(packet_path_obj)
    packet_file_sha256 = _packet_file_sha256_after_canonical_validation(packet_path_obj, packet)

    state = load_session(cwd)
    current_manuscript_sha = _file_sha256(state.artifacts.paper_full_tex)
    if packet.get("manuscript_sha256") != current_manuscript_sha:
        raise ContractError("operator review packet manuscript hash is stale for the current session")
    assert current_manuscript_sha is not None
    _validate_operator_packet_artifact_bindings(
        cwd=cwd,
        packet=packet,
        current_manuscript_sha256=current_manuscript_sha,
    )

    candidate_role = actionable_candidate_approval_role(packet)
    decision_kind = _resolve_decision_kind(answer, intent, candidate_role=candidate_role)
    actions = _human_needed_actions(packet)
    action = _select_action(actions, action_id, candidate_role=candidate_role if decision_kind == "approve_existing_candidate" else None)
    handoff_type = _classify_action(action, candidate_role=candidate_role if decision_kind == "approve_existing_candidate" else None)

    answer_sha256 = _sha256_text(answer)
    answer_id = f"answer-{answer_sha256[:16]}"
    raw_path = _private_answer_path(
        cwd,
        str(packet.get("session_id") or "unknown-session"),
        answer_id,
        output_answer,
        redacted_answer_only=redacted_answer_only,
    )
    private_answer_artifact_sha256: str | None = None
    if raw_path is not None:
        raw_payload = {
            "schema_version": HUMAN_NEEDED_ANSWER_SCHEMA_VERSION,
            "recorded_at": utc_now_iso(),
            "session_id": packet.get("session_id"),
            "packet_sha256": packet.get("packet_sha256"),
            "packet_file_sha256": packet_file_sha256,
            "manuscript_sha256": packet.get("manuscript_sha256"),
            "answer_sha256": answer_sha256,
            "answer": answer,
            "decision_kind": decision_kind,
            "handoff_type": handoff_type,
            "target_action_id": _action_id(action) or None,
        }
        write_json(raw_path, raw_payload)
        private_answer_artifact_sha256 = _sha256_file(raw_path)

    metadata = _metadata_without_targets(
        packet=packet,
        packet_file_sha256=packet_file_sha256,
        answer_sha256=answer_sha256,
        private_answer_artifact_sha256=private_answer_artifact_sha256,
        decision_kind=decision_kind,
        handoff_type=handoff_type,
        action=action,
        candidate_role=candidate_role if decision_kind == "approve_existing_candidate" else None,
    )
    draft = {
        "intent": decision_kind,
        "issues": [
            _draft_issue_for_action(
                action=action,
                handoff_type=handoff_type,
                decision_kind=decision_kind,
                candidate_role=candidate_role if decision_kind == "approve_existing_candidate" else None,
            )
        ],
        "human_needed_answer": metadata,
    }
    feedback = normalize_operator_feedback_draft(packet, draft)
    target_issue_ids = [str(issue.get("id") or "") for issue in feedback.get("issues") or [] if str(issue.get("id") or "")]
    metadata["target_issue_ids"] = target_issue_ids
    feedback["human_needed_answer"] = dict(metadata)

    feedback_path = Path(output_feedback).resolve() if output_feedback else artifact_path(cwd, "human_needed.operator_feedback.json")
    write_json(feedback_path, feedback)

    public_answer_artifact = artifact_path(cwd, "human_needed.answer.public.json")
    public_payload = dict(metadata)
    public_payload["schema_version"] = HUMAN_NEEDED_PUBLIC_SCHEMA_VERSION
    write_json(public_answer_artifact, public_payload)

    result = dict(public_payload)
    result["answer"] = "redacted"
    result["execution"] = "human_needed_answer_recorded"
    _attach_public_path_or_label(result, cwd, "feedback_path", feedback_path)
    result["feedback_sha256"] = _sha256_file(feedback_path)
    _attach_public_path_or_label(result, cwd, "packet_path", packet_path_obj)
    _attach_public_path_or_label(result, cwd, "public_answer_artifact", public_answer_artifact)
    result["public_answer_artifact_sha256"] = _sha256_file(public_answer_artifact)
    if apply:
        imported_path, imported = import_operator_feedback(
            cwd,
            packet_path=packet_path_obj,
            feedback_path=feedback_path,
            output_path=imported_feedback_output,
        )
        execution_path, execution = apply_operator_feedback(
            cwd,
            provider or MockProvider(),
            imported_feedback_path=imported_path,
            max_supervised_iterations=max_supervised_iterations,
            require_compile=require_compile,
            quality_mode=quality_mode,
            max_iterations=max_iterations,
            require_live_verification=require_live_verification,
            accept_mixed_provenance=accept_mixed_provenance,
            runtime_mode=runtime_mode,
            citation_evidence_mode=citation_evidence_mode,
            citation_provider_name=citation_provider_name,
            citation_provider_command=citation_provider_command,
        )
        _attach_public_path_or_label(result, cwd, "imported_feedback_path", imported_path)
        result["imported_feedback_sha256"] = _sha256_file(imported_path)
        _attach_public_path_or_label(result, cwd, "operator_feedback_execution_path", execution_path)
        result["operator_feedback_execution_sha256"] = _sha256_file(execution_path)
        result["operator_feedback_execution_summary"] = {
            "verdict": execution.get("verdict"),
            "promotion_status": execution.get("promotion_status"),
            "promotion_reason": execution.get("promotion_reason"),
            "supervised_iteration_index": execution.get("supervised_iteration_index"),
            "supervised_remaining": execution.get("supervised_remaining"),
            "candidate_branch": execution.get("candidate_branch"),
        }
    return result
