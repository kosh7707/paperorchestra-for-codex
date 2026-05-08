from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .critics import write_citation_support_review, write_section_review
from .boundary import sanitize_author_facing_text
from .io_utils import read_json, write_json
from .models import utc_now_iso
from .operator_feedback_packets import (
    _artifact_bound_manuscript_sha,
    _artifact_by_role,
    _artifact_payload,
    _artifact_record,
    _canonical_sha256,
    _execution_payload_opens_operator_review,
    _execution_payload_sha256,
    _file_sha256,
    _first_current_bound_existing,
    _first_existing,
    _latest_human_needed_execution,
    _normalized_sha,
    _operator_review_human_needed_artifacts,
    _packet_has_human_needed_context,
    _packet_sha256,
    _sha256_bytes,
    _sha256_digest,
    _sha256_prefixed,
    _snapshot_operator_packet_artifacts,
    _validate_current_operator_plan,
    _validate_operator_packet_artifact_bindings,
)
from .pipeline import (
    ContractError,
    compile_current_paper,
    refine_current_paper,
    record_current_validation_report,
    review_current_paper,
    write_figure_placement_review,
)
from .providers import BaseProvider, ProviderError, TransientProviderError, get_citation_support_provider
from .quality_loop import append_quality_loop_history, write_quality_eval, write_quality_loop_plan
from .session import artifact_path, load_session, runtime_root, save_session

OPERATOR_PACKET_SCHEMA_VERSION = "operator-review-packet/1"
OPERATOR_FEEDBACK_SCHEMA_VERSION = "operator-feedback/1"
OPERATOR_FEEDBACK_IMPORT_SCHEMA_VERSION = "operator-feedback-import/1"
OPERATOR_FEEDBACK_EXECUTION_SCHEMA_VERSION = "operator-feedback-execution/1"
OPERATOR_FEEDBACK_INCORPORATION_SCHEMA_VERSION = "operator-feedback-incorporation/1"

OPERATOR_SOURCE = "codex_operator"
OPERATOR_PUBLIC_ENTRYPOINTS = {
    "build-operator-review-packet",
    "import-operator-feedback",
    "apply-operator-feedback",
}
ACTIONABLE_FAILURE_OWNER_CATEGORIES = {
    "author",
    "experiment",
    "proof",
    "bibliography",
    "implementation",
    "execution_error",
}
OPERATOR_FEEDBACK_INTENTS = {
    "approve_existing_candidate",
    "generate_new_operator_candidate",
    "reject_candidate_with_reason",
}
OVERALL_CATASTROPHIC_DROP = 8.0
AXIS_CATASTROPHIC_DROP = 15.0
HUMAN_REVIEWABLE_NEW_TIER2_CODES = {
    "citation_support_manual_check",
}

def _review_scope(require_pdf: bool, review_scope: str | None, pdf_path: str | Path | None) -> str:
    if review_scope:
        if review_scope not in {"pdf_and_tex", "tex_only"}:
            raise ContractError("review_scope must be one of: pdf_and_tex, tex_only")
        if review_scope == "pdf_and_tex" and not _file_sha256(pdf_path):
            raise ContractError("review_scope=pdf_and_tex requires a current compiled PDF")
        return review_scope
    return "pdf_and_tex" if require_pdf or _file_sha256(pdf_path) else "tex_only"

def build_operator_review_packet(
    cwd: str | Path | None,
    *,
    output_path: str | Path | None = None,
    require_pdf: bool = False,
    review_scope: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Build the hash-bound packet an external OMX/Codex operator must review."""

    state = load_session(cwd)
    if not state.artifacts.paper_full_tex:
        raise ContractError("Need paper.full.tex before building an operator review packet.")
    paper_path = Path(state.artifacts.paper_full_tex).resolve()
    if not paper_path.exists():
        raise ContractError(f"paper.full.tex is missing: {paper_path}")
    paper_dir = paper_path.parent
    qa_plan_path, qa_execution_path, operator_execution_path = _operator_review_human_needed_artifacts(cwd)
    pdf_path = state.artifacts.compiled_pdf
    scope = _review_scope(require_pdf, review_scope, pdf_path)
    if require_pdf and scope != "pdf_and_tex":
        raise ContractError("require_pdf=True requires review_scope=pdf_and_tex")
    packet_path = Path(output_path).resolve() if output_path else artifact_path(cwd, "operator_review_packet.json")

    manuscript_sha256 = _file_sha256(paper_path)
    artifacts: list[dict[str, Any]] = []
    required_paper = _artifact_record("paper_full_tex", paper_path, required=True)
    assert required_paper is not None
    artifacts.append(required_paper)
    if scope == "pdf_and_tex":
        pdf_record = _artifact_record("compiled_pdf", pdf_path, required=True)
        assert pdf_record is not None
        artifacts.append(pdf_record)
    for role, artifact_source_path in [
        (
            "citation_support_review",
            _first_current_bound_existing(
                "citation_support_review",
                manuscript_sha256,
                paper_dir / "citation_support_review.json",
                artifact_path(cwd, "citation_support_review.json"),
            ),
        ),
        (
            "section_review",
            _first_current_bound_existing(
                "section_review",
                manuscript_sha256,
                state.artifacts.latest_section_review_json,
                paper_dir / "section_review.json",
                artifact_path(cwd, "section_review.json"),
            ),
        ),
        (
            "quality_eval",
            _first_current_bound_existing(
                "quality_eval",
                manuscript_sha256,
                artifact_path(cwd, "quality-eval.json"),
            ),
        ),
        ("qa_loop_plan", qa_plan_path),
        ("qa_loop_execution", qa_execution_path),
        ("operator_feedback_execution", operator_execution_path),
        ("source_obligations", _first_existing(state.artifacts.source_obligations_json, artifact_path(cwd, "source_obligations.json"))),
        ("ralph_brief", _first_existing(artifact_path(cwd, "ralph-brief.md"))),
        ("ralph_handoff", _first_existing(artifact_path(cwd, "ralph-handoff.json"))),
    ]:
        record = _artifact_record(role, artifact_source_path)
        if record:
            artifacts.append(record)
    artifacts = _snapshot_operator_packet_artifacts(packet_path, artifacts)

    packet: dict[str, Any] = {
        "schema_version": OPERATOR_PACKET_SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "session_id": state.session_id,
        "manuscript_sha256": manuscript_sha256,
        "review_scope": scope,
        "review_scope_rationale": "compiled PDF present and included" if scope == "pdf_and_tex" else "TeX-only operator review; compiled PDF absent or not required",
        "artifacts": artifacts,
        "operator_instructions": {
            "feedback_authoring": "external_omx_side",
            "source": OPERATOR_SOURCE,
            "not_independent_human_review": True,
            "must_not_claim_independent_review": True,
        },
    }
    assert manuscript_sha256 is not None
    _validate_operator_packet_artifact_bindings(
        cwd=cwd,
        packet=packet,
        current_manuscript_sha256=manuscript_sha256,
    )
    packet["packet_sha256"] = _packet_sha256(packet)
    write_json(packet_path, packet)
    return packet_path, packet

def _normalize_issue_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())

def derive_operator_issue_id(
    packet_sha256: str,
    *,
    source_artifact_role: str,
    source_item_key: str,
    target_section: str,
    rationale: str,
    suggested_action: str,
) -> str:
    issue_text = _normalize_issue_text(f"{rationale}\n{suggested_action}")
    issue_text_hash = _sha256_bytes(issue_text.encode("utf-8"))
    payload = {
        "packet_sha256": packet_sha256,
        "source_artifact_role": source_artifact_role,
        "source_item_key": source_item_key,
        "target_section": target_section,
        "issue_text_sha256": issue_text_hash,
    }
    return "opfb-" + _canonical_sha256(payload)[:20]

def _read_packet(path: str | Path) -> dict[str, Any]:
    packet = read_json(path)
    if not isinstance(packet, dict):
        raise ContractError("operator review packet must be a JSON object")
    if packet.get("schema_version") != OPERATOR_PACKET_SCHEMA_VERSION:
        raise ContractError("operator review packet has an unsupported schema_version")
    expected = _packet_sha256(packet)
    if packet.get("packet_sha256") != expected:
        raise ContractError("operator review packet hash does not match packet contents")
    for artifact in packet.get("artifacts") or []:
        if not isinstance(artifact, dict):
            raise ContractError("operator review packet artifact entry must be an object")
        actual = _file_sha256(artifact.get("path"))
        if not actual or actual != artifact.get("sha256"):
            raise ContractError(f"operator review packet artifact is missing or stale: {artifact.get('role')}")
    return packet

def _validate_operator_issue(issue: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    required = [
        "id",
        "source_artifact_role",
        "source_item_key",
        "target_section",
        "severity",
        "rationale",
        "suggested_action",
        "authority_class",
    ]
    missing = [key for key in required if not str(issue.get(key) or "").strip()]
    if missing:
        raise ContractError(f"operator feedback issue is missing required fields: {', '.join(missing)}")
    expected_id = derive_operator_issue_id(
        str(packet["packet_sha256"]),
        source_artifact_role=str(issue["source_artifact_role"]),
        source_item_key=str(issue["source_item_key"]),
        target_section=str(issue["target_section"]),
        rationale=str(issue["rationale"]),
        suggested_action=str(issue["suggested_action"]),
    )
    if issue.get("id") != expected_id:
        raise ContractError(f"operator feedback issue id is not derivable from packet: {issue.get('id')}")
    if issue.get("source") not in {None, OPERATOR_SOURCE}:
        raise ContractError("operator feedback issue source must be codex_operator")
    if issue.get("not_independent_human_review") not in {None, True}:
        raise ContractError("operator feedback issue must not claim independent human review")
    owner_category = str(issue.get("owner_category") or _owner_category_for_issue(issue))
    if owner_category not in ACTIONABLE_FAILURE_OWNER_CATEGORIES:
        raise ContractError(f"invalid owner_category for operator issue: {owner_category}")
    normalized = dict(issue)
    normalized["source"] = OPERATOR_SOURCE
    normalized["not_independent_human_review"] = True
    normalized["owner_category"] = owner_category
    return normalized

def _owner_category_for_issue(issue: dict[str, Any]) -> str:
    text = " ".join(str(issue.get(key) or "") for key in ("target_section", "rationale", "suggested_action", "authority_class")).lower()
    if any(token in text for token in ("experiment", "benchmark", "evaluation", "result")):
        return "experiment"
    if any(token in text for token in ("proof", "theorem", "security", "bound")):
        return "proof"
    if any(token in text for token in ("citation", "bibliography", "reference", "bibtex")):
        return "bibliography"
    if any(token in text for token in ("compile", "validation", "implementation", "execution")):
        return "implementation"
    return "author"

def _action_for_issue(issue: dict[str, Any]) -> dict[str, Any]:
    return {
        "action_id": f"operator-feedback:{issue['id']}",
        "code": "operator_feedback_issue",
        "automation": "semi_auto",
        "source_issue_id": issue["id"],
        "target_section": issue["target_section"],
        "authority_class": issue["authority_class"],
        "owner_category": issue["owner_category"],
        "reason": issue["rationale"],
        "suggested_action": issue["suggested_action"],
        "source": OPERATOR_SOURCE,
        "not_independent_human_review": True,
    }

def _normalize_operator_intent(feedback: dict[str, Any]) -> str:
    intents: list[str] = []
    raw_intents = feedback.get("intents")
    if isinstance(raw_intents, list):
        intents.extend(str(item) for item in raw_intents if str(item or "").strip())
    if str(feedback.get("intent") or "").strip():
        intents.append(str(feedback["intent"]))
    for issue in feedback.get("issues") or []:
        if isinstance(issue, dict) and str(issue.get("action_kind") or "").strip():
            intents.append(str(issue["action_kind"]))
    for action in feedback.get("actions") or []:
        if isinstance(action, dict) and str(action.get("action_kind") or "").strip():
            intents.append(str(action["action_kind"]))
    primary = str(feedback.get("primary_intent") or "").strip()
    normalized = [intent for intent in dict.fromkeys(intents) if intent]
    invalid = [intent for intent in normalized + ([primary] if primary else []) if intent and intent not in OPERATOR_FEEDBACK_INTENTS]
    if invalid:
        raise ContractError(f"unsupported operator feedback intent: {', '.join(invalid)}")
    if primary:
        if primary not in normalized and normalized:
            raise ContractError("operator feedback primary_intent must be included in intents")
        return primary
    if len(normalized) != 1:
        raise ContractError("operator feedback must include exactly one machine-readable intent or a primary_intent")
    return normalized[0]

def import_operator_feedback(
    cwd: str | Path | None,
    *,
    packet_path: str | Path,
    feedback_path: str | Path,
    output_path: str | Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    packet_path = Path(packet_path).resolve()
    feedback_path = Path(feedback_path).resolve()
    packet = _read_packet(packet_path)
    if not _packet_has_human_needed_context(packet):
        raise ContractError(
            "operator review packet does not include terminal human_needed plan "
            "or latest human_needed QA/operator-feedback execution evidence"
        )
    _validate_operator_packet_artifact_bindings(
        cwd=cwd,
        packet=packet,
        current_manuscript_sha256=str(packet.get("manuscript_sha256") or ""),
    )
    feedback = read_json(feedback_path)
    if not isinstance(feedback, dict):
        raise ContractError("operator feedback must be a JSON object")
    if feedback.get("schema_version") != OPERATOR_FEEDBACK_SCHEMA_VERSION:
        raise ContractError("operator feedback has an unsupported schema_version")
    if feedback.get("source") != OPERATOR_SOURCE or feedback.get("not_independent_human_review") is not True:
        raise ContractError("operator feedback must be labeled source=codex_operator and not_independent_human_review=true")
    if feedback.get("packet_sha256") != packet.get("packet_sha256"):
        raise ContractError("operator feedback packet_sha256 does not match packet")
    if feedback.get("manuscript_sha256") != packet.get("manuscript_sha256"):
        raise ContractError("operator feedback manuscript_sha256 does not match packet")
    intent = _normalize_operator_intent(feedback)
    issues = feedback.get("issues")
    if not isinstance(issues, list) or not issues:
        raise ContractError("operator feedback must include one or more issues")
    imported_issues = [_validate_operator_issue(issue, packet) for issue in issues if isinstance(issue, dict)]
    if len(imported_issues) != len(issues):
        raise ContractError("operator feedback issues must all be JSON objects")
    imported = {
        "schema_version": OPERATOR_FEEDBACK_IMPORT_SCHEMA_VERSION,
        "imported_at": utc_now_iso(),
        "session_id": packet.get("session_id"),
        "source": OPERATOR_SOURCE,
        "not_independent_human_review": True,
        "packet_path": str(packet_path),
        "packet_sha256": packet.get("packet_sha256"),
        "feedback_path": str(feedback_path),
        "feedback_sha256": _file_sha256(feedback_path),
        "manuscript_sha256": packet.get("manuscript_sha256"),
        "review_scope": packet.get("review_scope"),
        "intent": intent,
        "issues": imported_issues,
        "translated_actions": [_action_for_issue(issue) for issue in imported_issues],
    }
    path = Path(output_path).resolve() if output_path else artifact_path(cwd, "operator_feedback.imported.json")
    write_json(path, imported)
    return path, imported

def _load_imported_feedback(imported_feedback_path: str | Path) -> dict[str, Any]:
    payload = read_json(imported_feedback_path)
    if not isinstance(payload, dict) or payload.get("schema_version") != OPERATOR_FEEDBACK_IMPORT_SCHEMA_VERSION:
        raise ContractError("imported operator feedback has an unsupported schema_version")
    if payload.get("source") != OPERATOR_SOURCE or payload.get("not_independent_human_review") is not True:
        raise ContractError("imported operator feedback lost non-independent provenance")
    packet = _read_packet(payload.get("packet_path"))
    if payload.get("packet_sha256") != packet.get("packet_sha256"):
        raise ContractError("imported operator feedback packet hash is stale")
    return payload

def _operator_review_payload(imported: dict[str, Any]) -> dict[str, Any]:
    issues = imported.get("issues") or []
    top_improvements = [
        f"[{issue.get('id')}] "
        + sanitize_author_facing_text(issue.get("suggested_action"), fallback="Revise the target section using ordinary scholarly prose.")
        for issue in issues
    ]
    weaknesses = [
        f"[{issue.get('id')}] "
        + sanitize_author_facing_text(issue.get("rationale"), fallback="The target section needs ordinary scholarly revision.")
        for issue in issues
    ]
    issue_context = _operator_issue_context(imported)
    return {
        "schema_version": "operator-feedback-review/1",
        "source": OPERATOR_SOURCE,
        "not_independent_human_review": True,
        "manuscript_sha256": imported.get("manuscript_sha256"),
        "packet_sha256": imported.get("packet_sha256"),
        "summary": {"weaknesses": weaknesses, "top_improvements": top_improvements},
        "issue_context": issue_context,
        "questions": [],
        "penalties": [],
        "axis_scores": {},
        "writer_blind_to_reviewer_scores": True,
        "score_redaction": "operator feedback is issue-shaped and contains no reviewer scores",
    }

def _truncate_context_text(value: Any, *, limit: int = 800) -> str:
    text = sanitize_author_facing_text(value, fallback="")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"

def _packet_payload_by_role(packet: dict[str, Any], role: str) -> dict[str, Any] | None:
    record = _artifact_by_role(packet, role)
    if not record:
        return None
    try:
        payload = read_json(record["path"])
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None

def _problematic_citation_context(payload: dict[str, Any] | None, *, limit: int = 16) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    problematic_statuses = {
        "weakly_supported",
        "unsupported",
        "contradicted",
        "insufficient_evidence",
        "needs_manual_check",
        "manual_check",
        "metadata_only",
        "evidence_missing",
    }
    result: list[dict[str, Any]] = []
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        status = str(item.get("support_status") or item.get("status") or "").strip()
        if status not in problematic_statuses:
            continue
        result.append(
            {
                "id": item.get("id"),
                "support_status": status,
                "claim_type": item.get("claim_type"),
                "risk": item.get("risk"),
                "sentence": _truncate_context_text(item.get("sentence"), limit=900),
                "citation_keys": [str(key) for key in item.get("citation_keys") or []],
                "suggested_fix": _truncate_context_text(item.get("suggested_fix"), limit=500),
                "model_reasoning": _truncate_context_text(item.get("model_reasoning"), limit=700),
            }
        )
        if len(result) >= limit:
            break
    return result

def _high_risk_claim_context(payload: dict[str, Any] | None, *, limit: int = 16) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    tiers = payload.get("tiers") if isinstance(payload.get("tiers"), dict) else {}
    tier2 = tiers.get("tier_2_claim_safety") if isinstance(tiers.get("tier_2_claim_safety"), dict) else {}
    checks = tier2.get("checks") if isinstance(tier2.get("checks"), dict) else {}
    sweep = checks.get("high_risk_claim_sweep") if isinstance(checks.get("high_risk_claim_sweep"), dict) else {}
    result: list[dict[str, Any]] = []
    for item in sweep.get("items") or []:
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "line": item.get("line"),
                "sentence": _truncate_context_text(item.get("sentence"), limit=900),
                "reason": _truncate_context_text(item.get("reason"), limit=500),
            }
        )
        if len(result) >= limit:
            break
    return result

def _operator_issue_context(imported: dict[str, Any]) -> dict[str, Any]:
    """Attach concrete failing claim context to operator feedback for the writer.

    Human/operator feedback enters the refiner through the review JSON surface.
    The imported issue list is intentionally terse, so without this context the
    writer sees only abstract instructions such as "fix weak citation support"
    and cannot target the actual sentences that failed the critics.
    """
    packet_path = imported.get("packet_path")
    if not packet_path:
        return {}
    try:
        packet = _read_packet(packet_path)
    except Exception:
        return {}
    citation_review = _packet_payload_by_role(packet, "citation_support_review")
    quality_eval = _packet_payload_by_role(packet, "quality_eval")
    context = {
        "problematic_citation_items": _problematic_citation_context(citation_review),
        "high_risk_uncited_claims": _high_risk_claim_context(quality_eval),
        "writer_instruction": (
            "Use these concrete sentences as the primary repair targets. Do not add new bibliography keys; "
            "either ground each sentence with existing directly supporting evidence, soften it into scoped author-material prose, or remove it."
        ),
    }
    return {key: value for key, value in context.items() if value}

def _write_operator_review_for_refiner(cwd: str | Path | None, imported: dict[str, Any]) -> Path:
    path = artifact_path(cwd, "operator_feedback.redacted_review.json")
    write_json(path, _operator_review_payload(imported))
    return path

def _session_snapshot(cwd: str | Path | None) -> dict[str, Any]:
    state = load_session(cwd)
    paper_path = Path(state.artifacts.paper_full_tex).resolve() if state.artifacts.paper_full_tex else None
    return {
        "state": state.to_dict(),
        "paper_path": str(paper_path) if paper_path else None,
        "paper_text": paper_path.read_text(encoding="utf-8") if paper_path and paper_path.exists() else None,
    }

def _restore_session_snapshot(cwd: str | Path | None, snapshot: dict[str, Any]) -> None:
    from .models import SessionState

    paper_path = snapshot.get("paper_path")
    paper_text = snapshot.get("paper_text")
    if paper_path and paper_text is not None:
        Path(paper_path).write_text(paper_text, encoding="utf-8")
    state = SessionState.from_dict(snapshot["state"])
    save_session(cwd, state)

def _issue_incorporation(issues: list[dict[str, Any]], before_text: str, after_text: str, *, accepted: bool) -> list[dict[str, Any]]:
    return _issue_incorporation_detailed(issues, before_text, after_text, blocking_codes=[] if accepted else ["candidate_rejected"])

def _section_texts(latex: str) -> dict[str, str]:
    matches = list(re.finditer(r"\\section\*?\{([^}]+)\}", latex))
    if not matches:
        return {"Whole manuscript": latex}
    sections: dict[str, str] = {"Whole manuscript": latex}
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(latex)
        title = re.sub(r"\s+", " ", match.group(1)).strip()
        sections[title] = latex[start:end]
    return sections

def _section_for_target(sections: dict[str, str], target: str | None) -> str:
    if not target:
        return sections.get("Whole manuscript", "")
    normalized_target = re.sub(r"[^a-z0-9]+", "", target.lower())
    for title, text in sections.items():
        normalized_title = re.sub(r"[^a-z0-9]+", "", title.lower())
        if normalized_title and (normalized_title in normalized_target or normalized_target in normalized_title):
            return text
    return sections.get("Whole manuscript", "")

def _issue_terms(issue: dict[str, Any]) -> list[str]:
    text = f"{issue.get('rationale') or ''} {issue.get('suggested_action') or ''}"
    stop = {
        "the",
        "and",
        "that",
        "with",
        "into",
        "this",
        "from",
        "after",
        "before",
        "without",
        "should",
        "must",
        "section",
        "paper",
        "manuscript",
        "write",
        "rewrite",
        "add",
    }
    terms = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{4,}", text.lower()):
        if token not in stop and token not in terms:
            terms.append(token)
    return terms[:12]

def _issue_incorporation_detailed(
    issues: list[dict[str, Any]],
    before_text: str,
    after_text: str,
    *,
    blocking_codes: list[str],
) -> list[dict[str, Any]]:
    before_sections = _section_texts(before_text)
    after_sections = _section_texts(after_text)
    results: list[dict[str, Any]] = []
    for issue in issues:
        before_section = _section_for_target(before_sections, str(issue.get("target_section") or ""))
        after_section = _section_for_target(after_sections, str(issue.get("target_section") or ""))
        changed = before_section != after_section
        terms = _issue_terms(issue)
        matched_terms = [term for term in terms if term in after_section.lower()]
        if any(str(code).startswith(("unsupported", "numeric_grounding", "citation_coverage", "unknown_citation")) for code in blocking_codes):
            status = "blocked_by_claim_safety"
        elif changed and (matched_terms or not terms):
            status = "reflected"
        elif changed:
            status = "partially_reflected"
        elif blocking_codes:
            status = "needs_author_decision"
        else:
            status = "not_reflected"
        evidence = (
            "target section changed"
            if changed
            else "target section did not change"
        )
        results.append(
            {
                "issue_id": issue.get("id"),
                "status": status,
                "target_section": issue.get("target_section"),
                "owner_category": issue.get("owner_category"),
                "before_section_sha256": _sha256_prefixed(_sha256_bytes(before_section.encode("utf-8"))),
                "after_section_sha256": _sha256_prefixed(_sha256_bytes(after_section.encode("utf-8"))),
                "changed": changed,
                "matched_terms": matched_terms,
                "blocking_codes": blocking_codes,
                "evidence": evidence,
            }
        )
    return results

def _quality_failing_codes(quality_eval: dict[str, Any]) -> list[str]:
    result: list[str] = []
    tiers = quality_eval.get("tiers") if isinstance(quality_eval, dict) else {}
    if not isinstance(tiers, dict):
        return result
    for tier in tiers.values():
        if isinstance(tier, dict) and tier.get("status") in {"fail", "warn"}:
            result.extend(str(code) for code in tier.get("failing_codes") or [])
    return sorted(dict.fromkeys(result))

def _tier_failing_codes(quality_eval: dict[str, Any] | None, tier_name: str) -> list[str]:
    tiers = quality_eval.get("tiers") if isinstance(quality_eval, dict) else {}
    tier = tiers.get(tier_name) if isinstance(tiers, dict) else None
    if not isinstance(tier, dict):
        return []
    return sorted(dict.fromkeys(str(code) for code in tier.get("failing_codes") or []))

def _tier_status(quality_eval: dict[str, Any], tier_name: str) -> str:
    tiers = quality_eval.get("tiers") if isinstance(quality_eval, dict) else {}
    tier = tiers.get(tier_name) if isinstance(tiers, dict) else None
    return str(tier.get("status") or "pass") if isinstance(tier, dict) else "pass"

def _candidate_hard_gate(
    *,
    validation_payload: dict[str, Any],
    compile_payload: dict[str, Any] | None,
    quality_eval: dict[str, Any],
    quality_mode: str,
    incorporation: list[dict[str, Any]],
    candidate_result: dict[str, Any] | None,
    require_issue_progress: bool,
    manuscript_changed: bool,
    new_tier2_failures: list[str],
    base_active_failures: list[str],
    resolved_active_failures: list[str],
    allow_human_reviewable_new_tier2: bool = False,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if not manuscript_changed:
        reasons.append("no_textual_change")
        failure_category = str((candidate_result or {}).get("executor_failure_category") or "none")
        if failure_category != "none":
            reasons.append("executor_crashed")
        else:
            reasons.append("executor_returned_identical_content")
    if not validation_payload.get("ok"):
        reasons.append("validation_failed")
    if compile_payload and not compile_payload.get("ok"):
        reasons.append("compile_failed")
    if _tier_status(quality_eval, "tier_0_preconditions") == "fail":
        reasons.append("tier0_failed")
    if _tier_status(quality_eval, "tier_1_structural") == "fail":
        reasons.append("tier1_failed")
    hard_new_tier2_failures = [
        code
        for code in new_tier2_failures
        if not (allow_human_reviewable_new_tier2 and code in HUMAN_REVIEWABLE_NEW_TIER2_CODES)
    ]
    if quality_mode == "claim_safe" and hard_new_tier2_failures:
        reasons.append("tier2_claim_safety_new_failures")
    if base_active_failures and not resolved_active_failures and not _candidate_reduces_citation_issue_count(candidate_result):
        reasons.append("active_blocker_progress_missing")
    if require_issue_progress and not any(item["status"] in {"reflected", "partially_reflected"} for item in incorporation):
        reasons.append("issue_progress_missing")
    if _catastrophic_review_regression(candidate_result):
        reasons.append("reviewer_catastrophic_regression")
    return not reasons, reasons

def _candidate_reduces_citation_issue_count(candidate_result: dict[str, Any] | None) -> bool:
    progress = candidate_result.get("candidate_progress") if isinstance(candidate_result, dict) else None
    if not isinstance(progress, dict):
        return False
    citation_issue_delta = progress.get("citation_issue_delta")
    return progress.get("forward_progress") is True and isinstance(citation_issue_delta, int) and citation_issue_delta < 0

def _candidate_attempt_ready_for_human_review(attempt: dict[str, Any]) -> bool:
    if not attempt.get("resolved_active_failures"):
        return False
    if not attempt.get("candidate_path"):
        return False
    if not Path(str(attempt.get("candidate_path"))).exists():
        return False
    disqualifying_reasons = {
        "no_textual_change",
        "executor_crashed",
        "executor_returned_identical_content",
        "validation_failed",
        "compile_failed",
        "tier0_failed",
        "tier1_failed",
        "active_blocker_progress_missing",
        "issue_progress_missing",
        "reviewer_catastrophic_regression",
    }
    reasons = {str(reason) for reason in attempt.get("gate_reasons") or []}
    if reasons & disqualifying_reasons:
        return False
    new_tier2 = {str(code) for code in attempt.get("new_tier2_failures") or []}
    return new_tier2 <= HUMAN_REVIEWABLE_NEW_TIER2_CODES

def _best_human_review_candidate_attempt(attempts: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [attempt for attempt in attempts if _candidate_attempt_ready_for_human_review(attempt)]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda attempt: (
            len(attempt.get("resolved_active_failures") or []),
            -len(attempt.get("candidate_active_failures") or []),
            -int(attempt.get("attempt_index") or 0),
        ),
    )

def _citation_issue_count_from_summary(summary: dict[str, Any] | None) -> int | None:
    if not isinstance(summary, dict):
        return None
    total = 0
    found = False
    for key in (
        "weakly_supported",
        "unsupported",
        "insufficient_evidence",
        "needs_manual_check",
        "manual_check",
        "contradicted",
        "metadata_only",
        "evidence_missing",
    ):
        value = summary.get(key)
        if isinstance(value, int):
            found = True
            total += value
    return total if found else None

def _attach_candidate_approval_from_attempt(
    execution: dict[str, Any],
    attempt: dict[str, Any],
    *,
    execution_path: Path,
) -> None:
    before_codes = [str(code) for code in attempt.get("base_active_failures") or []]
    after_codes = [str(code) for code in attempt.get("candidate_active_failures") or []]
    before_hash = _sha256_prefixed(execution.get("manuscript_sha256_before"))
    after_hash = _sha256_prefixed(_file_sha256(attempt.get("candidate_path")))
    verification = attempt.get("verification") if isinstance(attempt.get("verification"), dict) else {}
    citation_summary = None
    citation_block = verification.get("citation_support_review") if isinstance(verification, dict) else None
    if isinstance(citation_block, dict):
        citation_summary = citation_block.get("summary")
    before_issue_count = None
    after_issue_count = _citation_issue_count_from_summary(citation_summary)
    progress = {
        "resolved_codes": [str(code) for code in attempt.get("resolved_active_failures") or []],
        "new_codes": [str(code) for code in attempt.get("candidate_active_failures") or [] if code not in before_codes],
        "before_failing_codes": before_codes,
        "after_failing_codes": after_codes,
        "before_manuscript_hash": before_hash,
        "after_manuscript_hash": after_hash,
        "same_manuscript_as_previous": before_hash == after_hash if before_hash and after_hash else None,
        "manuscript_identity_known": bool(before_hash and after_hash),
        "before_citation_issue_count": before_issue_count,
        "after_citation_issue_count": after_issue_count,
        "citation_issue_delta": (after_issue_count - before_issue_count) if isinstance(before_issue_count, int) and isinstance(after_issue_count, int) else None,
        "forward_progress": True,
    }
    approval = {
        "status": "human_needed_candidate_ready",
        "candidate_path": attempt.get("candidate_path"),
        "candidate_sha256": _sha256_prefixed(_sha256_digest(str(attempt.get("candidate_sha256") or "")) or _file_sha256(attempt.get("candidate_path"))),
        "base_manuscript_sha256": before_hash,
        "source_execution_path": str(execution_path),
        "source_execution_sha256": "",
        "created_at": utc_now_iso(),
        "reason": "supervised operator candidate made net progress but introduced only human-reviewable claim-safety uncertainty",
    }
    execution["candidate_approval"] = approval
    execution["candidate_progress"] = progress
    execution["candidate_state"] = {
        "manuscript_path": attempt.get("candidate_path"),
        "verification": verification,
        "after": {
            "failing_codes": after_codes,
            "citation_support_summary": citation_summary,
        },
        "quality_eval_path": (verification.get("quality_eval") or {}).get("path") if isinstance(verification.get("quality_eval"), dict) else None,
        "qa_loop_plan_path": (verification.get("qa_loop_plan") or {}).get("path") if isinstance(verification.get("qa_loop_plan"), dict) else None,
        "qa_loop_plan_verdict": (verification.get("qa_loop_plan") or {}).get("verdict") if isinstance(verification.get("qa_loop_plan"), dict) else None,
        "progress": progress,
    }
    approval["source_execution_sha256"] = _execution_payload_sha256(execution)

def _catastrophic_review_regression(candidate_result: dict[str, Any] | None) -> bool:
    if not candidate_result:
        return False
    before = candidate_result.get("score_before")
    after = candidate_result.get("score_after")
    if isinstance(before, (int, float)) and isinstance(after, (int, float)) and float(after) < float(before) - OVERALL_CATASTROPHIC_DROP:
        return True
    before_axes = candidate_result.get("axis_scores_before") or {}
    after_axes = candidate_result.get("axis_scores_after") or {}
    if isinstance(before_axes, dict) and isinstance(after_axes, dict):
        for key in set(before_axes) & set(after_axes):
            if isinstance(before_axes.get(key), (int, float)) and isinstance(after_axes.get(key), (int, float)):
                if float(after_axes[key]) < float(before_axes[key]) - AXIS_CATASTROPHIC_DROP:
                    return True
    return False

def _actionable_failure(owner_categories: list[str], reason: str, *, execution_error: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "reason": reason,
        "owner_categories": sorted(dict.fromkeys(owner_categories or ["author"])),
    }
    if execution_error:
        payload["execution_error"] = execution_error
    return payload

def _verification_snapshot(
    cwd: str | Path | None,
    *,
    provider: BaseProvider,
    require_compile: bool,
    quality_mode: str,
    max_iterations: int,
    require_live_verification: bool,
    accept_mixed_provenance: bool,
    runtime_mode: str,
    citation_evidence_mode: str,
    citation_provider_name: str | None,
    citation_provider_command: str | None,
    validation_name: str,
) -> dict[str, Any]:
    validation_path, validation_payload = record_current_validation_report(cwd, name=validation_name)
    compile_payload: dict[str, Any] | None = None
    if require_compile:
        try:
            pdf_path = compile_current_paper(cwd)
            compile_payload = {"ok": True, "pdf": str(pdf_path)}
        except Exception as exc:  # pragma: no cover - compile depends on local toolchain
            compile_payload = {"ok": False, "error": str(exc)}
    citation_provider = get_citation_support_provider(
        citation_provider_name or ("mock" if citation_evidence_mode == "heuristic" else "shell"),
        command=citation_provider_command,
        evidence_mode=citation_evidence_mode,
    )
    section_path = write_section_review(cwd)
    figure_path, figure_payload = write_figure_placement_review(cwd)
    citation_path = write_citation_support_review(cwd, provider=citation_provider, evidence_mode=citation_evidence_mode)
    review_path = review_current_paper(cwd, provider, runtime_mode=runtime_mode)
    quality_path, quality_eval = write_quality_eval(
        cwd,
        quality_mode=quality_mode,
        max_iterations=max_iterations,
        require_live_verification=require_live_verification,
    )
    plan_path, plan = write_quality_loop_plan(
        cwd,
        quality_mode=quality_mode,
        max_iterations=max_iterations,
        require_live_verification=require_live_verification,
        accept_mixed_provenance=accept_mixed_provenance,
        quality_eval_input_path=quality_path,
    )
    return {
        "validation_path": validation_path,
        "validation_payload": validation_payload,
        "compile_payload": compile_payload,
        "section_path": section_path,
        "figure_path": figure_path,
        "figure_payload": figure_payload,
        "citation_path": citation_path,
        "review_path": review_path,
        "quality_path": quality_path,
        "quality_eval": quality_eval,
        "plan_path": plan_path,
        "plan": plan,
    }

def _verification_block(verification: dict[str, Any]) -> dict[str, Any]:
    plan = verification.get("plan") or {}
    quality_eval = verification.get("quality_eval") if isinstance(verification.get("quality_eval"), dict) else {}
    source_artifacts = quality_eval.get("source_artifacts") if isinstance(quality_eval.get("source_artifacts"), dict) else {}
    citation_check = {}
    tiers = quality_eval.get("tiers") if isinstance(quality_eval.get("tiers"), dict) else {}
    tier2 = tiers.get("tier_2_claim_safety") if isinstance(tiers.get("tier_2_claim_safety"), dict) else {}
    checks = tier2.get("checks") if isinstance(tier2.get("checks"), dict) else {}
    if isinstance(checks.get("citation_support_critic"), dict):
        citation_check = checks["citation_support_critic"]
    return {
        "validate_current": {
            "path": str(verification["validation_path"]),
            "ok": verification["validation_payload"].get("ok"),
        },
        "compile": verification.get("compile_payload"),
        "section_review": {"path": str(verification["section_path"])},
        "figure_placement_review": {
            "path": str(verification["figure_path"]),
            "manuscript_sha256": (verification.get("figure_payload") or {}).get("manuscript_sha256"),
        },
        "citation_support_review": {
            "path": str(verification["citation_path"]),
            "sha256": source_artifacts.get("citation_review_sha256") or citation_check.get("citation_review_sha256"),
            "summary": citation_check.get("canonical_summary") or citation_check.get("summary"),
        },
        "review": {"path": str(verification["review_path"])},
        "quality_eval": {
            "path": str(verification["quality_path"]),
            "citation_review_sha256": source_artifacts.get("citation_review_sha256"),
        },
        "qa_loop_plan": {"path": str(verification["plan_path"]), "verdict": plan.get("verdict")},
    }

def _load_packet_from_imported(imported: dict[str, Any]) -> dict[str, Any]:
    return _read_packet(imported.get("packet_path"))

def _packet_artifact_payload(packet: dict[str, Any], role: str) -> dict[str, Any] | None:
    record = _artifact_by_role(packet, role)
    if not record:
        return None
    payload = read_json(record["path"])
    return payload if isinstance(payload, dict) else None

def _candidate_approval_source_role(imported: dict[str, Any]) -> str | None:
    roles = {
        str(issue.get("source_artifact_role") or "")
        for issue in imported.get("issues") or []
        if isinstance(issue, dict) and str(issue.get("source_artifact_role") or "") in {"qa_loop_execution", "operator_feedback_execution"}
    }
    if len(roles) > 1:
        raise ContractError("approve_existing_candidate feedback must target exactly one candidate approval source artifact")
    return next(iter(roles), None)

def _candidate_source_execution_from_packet(packet: dict[str, Any], preferred_role: str | None = None) -> tuple[dict[str, Any], str]:
    roles = (preferred_role,) if preferred_role else ("qa_loop_execution", "operator_feedback_execution")
    for role in roles:
        if role not in {"qa_loop_execution", "operator_feedback_execution"}:
            raise ContractError("approve_existing_candidate targets an unsupported candidate approval source artifact")
        payload = _packet_artifact_payload(packet, role)
        if isinstance(payload, dict) and isinstance(payload.get("candidate_approval"), dict):
            return payload, role
        if role == "operator_feedback_execution" and isinstance(payload, dict):
            candidate_result = payload.get("candidate_result")
            if isinstance(candidate_result, dict):
                source_execution = candidate_result.get("source_execution")
                if isinstance(source_execution, dict) and isinstance(source_execution.get("candidate_approval"), dict):
                    return source_execution, role
    raise ContractError("approve_existing_candidate requires candidate approval execution evidence")

def _ready_candidate_from_packet(packet: dict[str, Any], current_sha: str | None, *, source_artifact_role: str | None = None) -> dict[str, Any]:
    execution, execution_role = _candidate_source_execution_from_packet(packet, source_artifact_role)
    approval = execution.get("candidate_approval") if isinstance(execution, dict) else None
    progress = execution.get("candidate_progress") if isinstance(execution, dict) else None
    candidate_state = execution.get("candidate_state") if isinstance(execution, dict) else None
    restored_current_state = execution.get("restored_current_state") if isinstance(execution, dict) else None
    if not isinstance(approval, dict) or approval.get("status") != "human_needed_candidate_ready":
        raise ContractError("approve_existing_candidate requires human_needed_candidate_ready evidence")
    missing_approval = [
        key
        for key in (
            "candidate_path",
            "candidate_sha256",
            "base_manuscript_sha256",
            "source_execution_path",
            "source_execution_sha256",
            "created_at",
        )
        if not str(approval.get(key) or "").strip()
    ]
    if missing_approval:
        raise ContractError("approve_existing_candidate missing candidate_approval." + ", candidate_approval.".join(missing_approval))
    if not isinstance(progress, dict) or progress.get("forward_progress") is not True:
        raise ContractError("approve_existing_candidate requires candidate_progress.forward_progress=true")
    for key in ("before_failing_codes", "after_failing_codes"):
        if key not in progress:
            raise ContractError(f"approve_existing_candidate missing candidate_progress.{key}")
    before_progress_codes = {str(code) for code in progress.get("before_failing_codes") or []}
    after_progress_codes = {str(code) for code in progress.get("after_failing_codes") or []}
    citation_issue_delta = progress.get("citation_issue_delta")
    citation_issue_count_improved = isinstance(citation_issue_delta, int) and citation_issue_delta < 0
    if before_progress_codes and not (before_progress_codes - after_progress_codes) and not citation_issue_count_improved:
        raise ContractError("approve_existing_candidate requires resolved active blockers or reduced citation issue count")
    candidate_verification = candidate_state.get("verification") if isinstance(candidate_state, dict) else None
    restored_verification = restored_current_state.get("verification") if isinstance(restored_current_state, dict) else None
    if not isinstance(candidate_verification, dict) and not isinstance(restored_verification, dict):
        raise ContractError("approve_existing_candidate requires candidate_state.verification or restored_current_state.verification")
    candidate_path = Path(str(approval.get("candidate_path") or "")).resolve()
    if not candidate_path.exists() or not candidate_path.is_file():
        raise ContractError("approved QA candidate file is missing")
    expected_candidate = _sha256_digest(str(approval.get("candidate_sha256") or ""))
    actual_candidate = _file_sha256(candidate_path)
    if not expected_candidate or expected_candidate != actual_candidate:
        raise ContractError("approved QA candidate hash mismatch")
    expected_base = _sha256_digest(str(approval.get("base_manuscript_sha256") or ""))
    if expected_base and current_sha and expected_base != current_sha:
        raise ContractError("approved QA candidate base manuscript hash mismatch")
    expected_source_sha = str(approval.get("source_execution_sha256") or "")
    actual_source_sha = _execution_payload_sha256(execution)
    source_path = approval.get("source_execution_path")
    source_record = _artifact_by_role(packet, execution_role)
    if source_path and source_record:
        approved_source = Path(str(source_path)).resolve()
        packet_sources = {Path(str(source_record["path"])).resolve()}
        if source_record.get("original_path"):
            packet_sources.add(Path(str(source_record["original_path"])).resolve())
        # Operator-feedback executions can carry a nested candidate_result
        # produced by an earlier QA-loop execution.  In that shape, the
        # approval's source_execution_path legitimately points at the embedded
        # QA execution, not the outer operator-feedback packet artifact.  The
        # hash check below is the binding proof that the embedded source is the
        # exact approval source reviewed by the operator.
        embedded_operator_source = execution_role == "operator_feedback_execution" and expected_source_sha == actual_source_sha
        if approved_source not in packet_sources and not embedded_operator_source:
            raise ContractError("approved QA candidate source execution path mismatch")
    if expected_source_sha != actual_source_sha:
        raise ContractError("approved QA candidate source execution hash mismatch")
    return {
        "candidate_path": str(candidate_path),
        "candidate_sha256": _sha256_prefixed(actual_candidate),
        "candidate_approval": approval,
        "candidate_progress": progress,
        "candidate_state": candidate_state,
        "source_execution": execution,
        "executor_environment": "preexisting_candidate",
        "executor_path": "operator_feedback._ready_candidate_from_packet",
        "executor_trace_artifact": str(source_path),
        "executor_failure_category": "none",
        "executor_source_role": execution_role,
    }

def _install_candidate_text(cwd: str | Path | None, candidate_path: str | Path) -> str:
    state = load_session(cwd)
    paper_path = Path(state.artifacts.paper_full_tex).resolve()
    candidate_text = Path(candidate_path).read_text(encoding="utf-8")
    paper_path.write_text(candidate_text, encoding="utf-8")
    state.artifacts.paper_full_tex = str(paper_path)
    state.active_artifact = paper_path.name
    save_session(cwd, state)
    return candidate_text

def _stage_candidate_text_for_verification(cwd: str | Path | None, candidate_path: str | Path) -> str:
    state = load_session(cwd)
    candidate = Path(candidate_path).resolve()
    candidate_text = candidate.read_text(encoding="utf-8")
    state.artifacts.paper_full_tex = str(candidate)
    state.active_artifact = candidate.name
    save_session(cwd, state)
    return candidate_text

def _preserve_operator_candidate_for_attempt(
    cwd: str | Path | None,
    candidate_result: dict[str, Any],
    *,
    attempt_index: int,
) -> dict[str, Any]:
    candidate_path = candidate_result.get("candidate_path")
    if not candidate_path:
        return candidate_result
    source = Path(str(candidate_path)).resolve()
    if not source.exists() or not source.is_file():
        return candidate_result
    preserved = artifact_path(cwd, f"paper.operator-feedback.attempt-{attempt_index:02d}.candidate.tex")
    preserved.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    updated = dict(candidate_result)
    updated.setdefault("raw_candidate_path", str(source))
    updated["candidate_path"] = str(preserved)
    updated["candidate_sha256"] = _sha256_prefixed(_file_sha256(preserved))
    updated["candidate_preservation_path"] = str(preserved)
    return updated

def _promote_candidate_text(cwd: str | Path | None, candidate_path: str | Path, canonical_path: str | Path | None) -> str:
    if not canonical_path:
        raise ContractError("cannot promote candidate without a canonical manuscript path")
    canonical = Path(canonical_path).resolve()
    candidate_text = Path(candidate_path).read_text(encoding="utf-8")
    canonical.write_text(candidate_text, encoding="utf-8")
    state = load_session(cwd)
    state.artifacts.paper_full_tex = str(canonical)
    state.active_artifact = canonical.name
    save_session(cwd, state)
    return candidate_text

def _generate_operator_candidate(
    cwd: str | Path | None,
    provider: BaseProvider,
    imported: dict[str, Any],
    *,
    require_compile: bool,
    runtime_mode: str,
    quality_mode: str,
) -> dict[str, Any]:
    redacted_review_path = _write_operator_review_for_refiner(cwd, imported)
    state = load_session(cwd)
    previous_review = state.artifacts.latest_review_json
    state.artifacts.latest_review_json = str(redacted_review_path)
    save_session(cwd, state)
    try:
        result = refine_current_paper(
            cwd,
            provider,
            iterations=1,
            require_compile_for_accept=require_compile,
            runtime_mode=runtime_mode,
            claim_safe=quality_mode == "claim_safe",
            candidate_only=True,
        )
    finally:
        state = load_session(cwd)
        state.artifacts.latest_review_json = previous_review
        save_session(cwd, state)
    item = result[-1] if result else {}
    candidate_path = item.get("candidate_path")
    if candidate_path and Path(candidate_path).exists():
        candidate_text = Path(candidate_path).read_text(encoding="utf-8")
    else:
        state = load_session(cwd)
        candidate_path = state.artifacts.paper_full_tex
        candidate_text = Path(candidate_path).read_text(encoding="utf-8") if candidate_path else ""
    item = dict(item)
    item.setdefault("candidate_path", candidate_path)
    item.setdefault("candidate_sha256", _file_sha256(candidate_path))
    item["previous_review_json"] = previous_review
    item["candidate_text"] = candidate_text
    item.setdefault("executor_environment", "in_process")
    item.setdefault("executor_path", "operator_feedback._generate_operator_candidate->pipeline.refine_current_paper")
    item.setdefault("executor_trace_artifact", str(redacted_review_path))
    item.setdefault("executor_failure_category", "none")
    return item

def _executor_failure_category(exc: Exception) -> str:
    if isinstance(exc, TransientProviderError):
        return "provider_transient_retry_exhausted"
    if isinstance(exc, ProviderError):
        return "provider_error"
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, ContractError):
        message = str(exc).lower()
        if "extract" in message or "latex" in message or "json" in message:
            return "extraction_failed"
        return "contract_error"
    return "unexpected_exception"

def _failed_operator_candidate_result(cwd: str | Path | None, exc: Exception, *, trace_artifact: str | None = None) -> dict[str, Any]:
    state = load_session(cwd)
    candidate_path = state.artifacts.paper_full_tex
    if trace_artifact is None:
        trace_path = artifact_path(cwd, "operator_feedback.executor-error.json")
        write_json(
            trace_path,
            {
                "schema_version": "operator-feedback-executor-error/1",
                "recorded_at": utc_now_iso(),
                "executor_environment": "in_process",
                "executor_path": "operator_feedback._generate_operator_candidate->pipeline.refine_current_paper",
                "executor_failure_category": _executor_failure_category(exc),
                "error_type": type(exc).__name__,
            },
        )
        trace_artifact = str(trace_path)
    return {
        "iteration": 1,
        "accepted": False,
        "candidate_only": True,
        "candidate_path": candidate_path,
        "candidate_sha256": _file_sha256(candidate_path),
        "candidate_text": Path(candidate_path).read_text(encoding="utf-8") if candidate_path and Path(candidate_path).exists() else "",
        "executor_environment": "in_process",
        "executor_path": "operator_feedback._generate_operator_candidate->pipeline.refine_current_paper",
        "executor_trace_artifact": trace_artifact,
        "executor_failure_category": _executor_failure_category(exc),
        "executor_error_type": type(exc).__name__,
    }

def apply_operator_feedback(
    cwd: str | Path | None,
    provider: BaseProvider,
    *,
    imported_feedback_path: str | Path,
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
) -> tuple[Path, dict[str, Any]]:
    if max_supervised_iterations < 1:
        raise ContractError("max_supervised_iterations must be >= 1")
    imported_path = Path(imported_feedback_path).resolve()
    imported = _load_imported_feedback(imported_path)
    packet = _load_packet_from_imported(imported)
    intent = str(imported.get("intent") or "")
    state = load_session(cwd)
    current_sha = _file_sha256(state.artifacts.paper_full_tex)
    if current_sha != imported.get("manuscript_sha256"):
        raise ContractError("imported operator feedback is stale for the current manuscript")
    base_quality_eval = _packet_artifact_payload(packet, "quality_eval")
    base_tier2_failures = set(_tier_failing_codes(base_quality_eval, "tier_2_claim_safety"))
    base_active_failures = set(_quality_failing_codes(base_quality_eval or {}))

    execution: dict[str, Any] = {
        "schema_version": OPERATOR_FEEDBACK_EXECUTION_SCHEMA_VERSION,
        "started_at": utc_now_iso(),
        "event_type": "operator_feedback_cycle",
        "source": OPERATOR_SOURCE,
        "not_independent_human_review": True,
        "imported_feedback_path": str(imported_path),
        "imported_feedback_sha256": _file_sha256(imported_path),
        "packet_sha256": imported.get("packet_sha256"),
        "manuscript_sha256_before": current_sha,
        "supervised_max_iterations": max_supervised_iterations,
        "translated_actions": imported.get("translated_actions") or [],
        "candidate_branch": intent,
        "promotion_status": "candidate_ready",
        "post_promotion_qa_verdict": None,
        "attempts": [],
        "verification": {},
    }
    snapshot = _session_snapshot(cwd)
    before_text = snapshot.get("paper_text") or ""
    owner_categories = [str(issue.get("owner_category") or "author") for issue in imported.get("issues") or []]
    final_incorporation: list[dict[str, Any]] = []
    final_verification: dict[str, Any] | None = None
    final_candidate_result: dict[str, Any] | None = None

    try:
        attempts = 0 if intent == "reject_candidate_with_reason" else 1 if intent == "approve_existing_candidate" else max_supervised_iterations
        for attempt_index in range(1, attempts + 1):
            _restore_session_snapshot(cwd, snapshot)
            if intent == "approve_existing_candidate":
                candidate_result = _ready_candidate_from_packet(
                    packet,
                    current_sha,
                    source_artifact_role=_candidate_approval_source_role(imported),
                )
                candidate_text = _stage_candidate_text_for_verification(cwd, candidate_result["candidate_path"])
                require_issue_progress = False
            elif intent == "generate_new_operator_candidate":
                try:
                    candidate_result = _generate_operator_candidate(
                        cwd,
                        provider,
                        imported,
                        require_compile=require_compile,
                        runtime_mode=runtime_mode,
                        quality_mode=quality_mode,
                    )
                except Exception as exc:
                    _restore_session_snapshot(cwd, snapshot)
                    candidate_result = _failed_operator_candidate_result(cwd, exc)
                candidate_text = candidate_result.get("candidate_text") or ""
                if candidate_result.get("candidate_path"):
                    candidate_result = _preserve_operator_candidate_for_attempt(
                        cwd,
                        candidate_result,
                        attempt_index=attempt_index,
                    )
                    candidate_text = _stage_candidate_text_for_verification(cwd, candidate_result["candidate_path"])
                require_issue_progress = True
            elif intent == "reject_candidate_with_reason":  # pragma: no cover - attempts is zero for explicit rejection
                break
            else:  # pragma: no cover - import validation should prevent this
                raise ContractError(f"unsupported imported operator intent: {intent}")

            verification = _verification_snapshot(
                cwd,
                provider=provider,
                require_compile=require_compile,
                quality_mode=quality_mode,
                max_iterations=max_iterations,
                require_live_verification=require_live_verification,
                accept_mixed_provenance=accept_mixed_provenance,
                runtime_mode=runtime_mode,
                citation_evidence_mode=citation_evidence_mode,
                citation_provider_name=citation_provider_name,
                citation_provider_command=citation_provider_command,
                validation_name=f"validation.operator-feedback.attempt-{attempt_index:02d}.json",
            )
            blocking_codes = _quality_failing_codes(verification["quality_eval"])
            candidate_tier2_failures = set(_tier_failing_codes(verification["quality_eval"], "tier_2_claim_safety"))
            candidate_active_failures = set(blocking_codes)
            new_tier2_failures = sorted(candidate_tier2_failures - base_tier2_failures)
            resolved_active_failures = sorted(base_active_failures - candidate_active_failures)
            incorporation_blocking_codes = [code for code in blocking_codes if code not in base_tier2_failures]
            incorporation = _issue_incorporation_detailed(imported.get("issues") or [], before_text, candidate_text, blocking_codes=incorporation_blocking_codes)
            candidate_sha = _file_sha256(load_session(cwd).artifacts.paper_full_tex)
            ok, gate_reasons = _candidate_hard_gate(
                validation_payload=verification["validation_payload"],
                compile_payload=verification["compile_payload"],
                quality_eval=verification["quality_eval"],
                quality_mode=quality_mode,
                incorporation=incorporation,
                candidate_result=candidate_result,
                require_issue_progress=require_issue_progress,
                manuscript_changed=candidate_sha != current_sha,
                new_tier2_failures=new_tier2_failures,
                base_active_failures=sorted(base_active_failures),
                resolved_active_failures=resolved_active_failures,
                allow_human_reviewable_new_tier2=intent == "approve_existing_candidate",
            )
            attempt_record = {
                "attempt_index": attempt_index,
                "candidate_branch": intent,
                "candidate_path": candidate_result.get("candidate_path"),
                "candidate_sha256": _sha256_prefixed(_sha256_digest(str(candidate_result.get("candidate_sha256") or "")) or _file_sha256(candidate_result.get("candidate_path"))),
                "gate_passed": ok,
                "gate_reasons": gate_reasons,
                "base_tier2_failures": sorted(base_tier2_failures),
                "candidate_tier2_failures": sorted(candidate_tier2_failures),
                "new_tier2_failures": new_tier2_failures,
                "base_active_failures": sorted(base_active_failures),
                "candidate_active_failures": sorted(candidate_active_failures),
                "resolved_active_failures": resolved_active_failures,
                "verification": _verification_block(verification),
                "incorporation": incorporation,
                "executor_environment": candidate_result.get("executor_environment") or ("preexisting_candidate" if intent == "approve_existing_candidate" else "in_process"),
                "executor_path": candidate_result.get("executor_path") or ("operator_feedback._ready_candidate_from_packet" if intent == "approve_existing_candidate" else "operator_feedback._generate_operator_candidate->pipeline.refine_current_paper"),
                "executor_trace_artifact": candidate_result.get("executor_trace_artifact"),
                "executor_failure_category": candidate_result.get("executor_failure_category") or "none",
            }
            execution["attempts"].append(attempt_record)
            final_incorporation = incorporation
            final_verification = verification
            final_candidate_result = candidate_result
            if ok:
                execution["promotion_status"] = "promoted"
                execution["promotion_reason"] = "operator_candidate_passed_hard_gate"
                _promote_candidate_text(cwd, candidate_result["candidate_path"], snapshot.get("paper_path"))
                promoted_verification = _verification_snapshot(
                    cwd,
                    provider=provider,
                    require_compile=require_compile,
                    quality_mode=quality_mode,
                    max_iterations=max_iterations,
                    require_live_verification=require_live_verification,
                    accept_mixed_provenance=accept_mixed_provenance,
                    runtime_mode=runtime_mode,
                    citation_evidence_mode=citation_evidence_mode,
                    citation_provider_name=citation_provider_name,
                    citation_provider_command=citation_provider_command,
                    validation_name=f"validation.operator-feedback.promoted-{attempt_index:02d}.json",
                )
                final_verification = promoted_verification
                execution["post_promotion_qa_verdict"] = str(promoted_verification["plan"].get("verdict"))
                attempt_record["promoted_canonical_verification"] = _verification_block(promoted_verification)
                break
        else:
            _restore_session_snapshot(cwd, snapshot)
            rollback_verification = _verification_snapshot(
                cwd,
                provider=provider,
                require_compile=require_compile,
                quality_mode=quality_mode,
                max_iterations=max_iterations,
                require_live_verification=require_live_verification,
                accept_mixed_provenance=accept_mixed_provenance,
                runtime_mode=runtime_mode,
                citation_evidence_mode=citation_evidence_mode,
                citation_provider_name=citation_provider_name,
                citation_provider_command=citation_provider_command,
                validation_name="validation.operator-feedback.rollback.json",
            )
            final_verification = rollback_verification
            explicit_rejection = intent == "reject_candidate_with_reason"
            execution["promotion_status"] = "rolled_back"
            execution["promotion_reason"] = "operator_rejected_candidate" if explicit_rejection else "operator_candidate_failed_hard_gate"
            execution["candidate_rollback"] = {
                "reason": "operator_rejected_candidate" if explicit_rejection else "supervised_candidate_failed_hard_gate",
                "restored_verification": _verification_block(rollback_verification),
            }

        execution_path = artifact_path(cwd, "operator_feedback.execution.json")
        promoted = execution["promotion_status"] == "promoted"
        executor_crashed = any(
            str(attempt.get("executor_failure_category") or "none") != "none"
            for attempt in execution.get("attempts") or []
        )
        if not promoted and final_verification is None:
            final_verification = _verification_snapshot(
                cwd,
                provider=provider,
                require_compile=False,
                quality_mode=quality_mode,
                max_iterations=max_iterations,
                require_live_verification=require_live_verification,
                accept_mixed_provenance=accept_mixed_provenance,
                runtime_mode=runtime_mode,
                citation_evidence_mode=citation_evidence_mode,
                citation_provider_name=citation_provider_name,
                citation_provider_command=citation_provider_command,
                validation_name="validation.operator-feedback.no-promotion.json",
            )
        final_state = load_session(cwd)
        after_sha = _file_sha256(final_state.artifacts.paper_full_tex)
        incorporation_report = {
            "schema_version": OPERATOR_FEEDBACK_INCORPORATION_SCHEMA_VERSION,
            "generated_at": utc_now_iso(),
            "source": OPERATOR_SOURCE,
            "not_independent_human_review": True,
            "packet_sha256": imported.get("packet_sha256"),
            "manuscript_sha256_before": current_sha,
            "manuscript_sha256_after": after_sha,
            "promotion_status": execution["promotion_status"],
            "actionable_failure": None if promoted else _actionable_failure(owner_categories, "operator feedback explicitly rejected the candidate" if intent == "reject_candidate_with_reason" else "operator feedback did not produce an acceptable canonical manuscript update"),
            "issues": final_incorporation,
        }
        incorporation_path = artifact_path(cwd, "operator_feedback.incorporation.json")
        write_json(incorporation_path, incorporation_report)
        plan = final_verification["plan"] if final_verification else {}
        verdict = "execution_error" if executor_crashed else str(plan.get("verdict") or "human_needed") if promoted else "human_needed"
        execution.update(
            {
                "completed_at": utc_now_iso(),
                "verdict": verdict,
                "supervised_iteration_index": len(execution["attempts"]),
                "supervised_remaining": max(max_supervised_iterations - len(execution["attempts"]), 0),
                "supervised_budget_exhausted": not promoted and len(execution["attempts"]) >= max_supervised_iterations,
                "manuscript_sha256_after": after_sha,
                "candidate_result": final_candidate_result,
                "incorporation_report": str(incorporation_path),
                "verification": _verification_block(final_verification) if final_verification else {},
                "actionable_failure": None if promoted else _actionable_failure(owner_categories, "operator feedback explicitly rejected the candidate" if intent == "reject_candidate_with_reason" else "operator feedback did not produce an acceptable canonical manuscript update"),
            }
        )
        if not promoted:
            best_attempt = _best_human_review_candidate_attempt(execution.get("attempts") or [])
            if best_attempt is not None:
                _attach_candidate_approval_from_attempt(
                    execution,
                    best_attempt,
                    execution_path=execution_path,
                )
        if executor_crashed:
            execution["error"] = "operator executor crashed during supervised feedback application"
        write_json(execution_path, execution)
        if final_verification:
            append_quality_loop_history(
                cwd,
                final_verification["quality_eval"],
                verdict=verdict,
                plan_path=final_verification["plan_path"],
                quality_eval_path=final_verification["quality_path"],
                execution_path=execution_path,
                event_type="operator_feedback_cycle",
                consumes_budget=False,
                extra={
                    "supervised_iteration_index": execution["supervised_iteration_index"],
                    "supervised_max_iterations": execution["supervised_max_iterations"],
                    "supervised_remaining": execution["supervised_remaining"],
                    "supervised_budget_exhausted": execution["supervised_budget_exhausted"],
                    "promotion_status": execution["promotion_status"],
                    "post_promotion_qa_verdict": execution["post_promotion_qa_verdict"],
                },
            )
        return execution_path, execution
    except Exception as exc:
        _restore_session_snapshot(cwd, snapshot)
        rollback_verification: dict[str, Any] | None = None
        try:
            rollback_verification = _verification_snapshot(
                cwd,
                provider=provider,
                require_compile=False,
                quality_mode=quality_mode,
                max_iterations=max_iterations,
                require_live_verification=require_live_verification,
                accept_mixed_provenance=accept_mixed_provenance,
                runtime_mode=runtime_mode,
                citation_evidence_mode=citation_evidence_mode,
                citation_provider_name=citation_provider_name,
                citation_provider_command=citation_provider_command,
                validation_name="validation.operator-feedback.exception-rollback.json",
            )
        except Exception as verify_exc:  # pragma: no cover - defensive evidence best-effort
            rollback_verification = {"error": type(verify_exc).__name__ + ": " + str(verify_exc)}
        restored_block: dict[str, Any] = {}
        if rollback_verification and "validation_path" in rollback_verification:
            restored_block = _verification_block(rollback_verification)
        elif rollback_verification:
            restored_block = {"error": rollback_verification.get("error")}
        execution.update(
            {
                "completed_at": utc_now_iso(),
                "verdict": "execution_error",
                "promotion_status": "rolled_back",
                "post_promotion_qa_verdict": None,
                "error": str(exc),
                "candidate_rollback": {"reason": "exception", "restored_verification": restored_block},
                "verification": {"restored_after_exception": restored_block},
                "actionable_failure": _actionable_failure(owner_categories, "supervised operator feedback command failed", execution_error=type(exc).__name__ + ": " + str(exc)),
            }
        )
        execution_path = artifact_path(cwd, "operator_feedback.execution.json")
        write_json(execution_path, execution)
        if rollback_verification and "quality_eval" in rollback_verification:
            append_quality_loop_history(
                cwd,
                rollback_verification["quality_eval"],
                verdict="execution_error",
                plan_path=rollback_verification["plan_path"],
                quality_eval_path=rollback_verification["quality_path"],
                execution_path=execution_path,
                event_type="operator_feedback_cycle",
                consumes_budget=False,
                extra={
                    "supervised_iteration_index": len(execution.get("attempts") or []) or 1,
                    "supervised_max_iterations": execution["supervised_max_iterations"],
                    "supervised_remaining": max(execution["supervised_max_iterations"] - (len(execution.get("attempts") or []) or 1), 0),
                    "supervised_budget_exhausted": True,
                    "execution_error": type(exc).__name__ + ": " + str(exc),
                    "promotion_status": "rolled_back",
                },
            )
        return execution_path, execution
