from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.boundary import sanitize_author_facing_text
from paperorchestra.core.io import write_json
from paperorchestra.core.session import artifact_path
from paperorchestra.feedback.operator_contract import OPERATOR_SOURCE


def _operator_review_payload(imported: dict[str, Any], *, prior_attempts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
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
    issue_context = _operator_issue_context(imported, prior_attempts=prior_attempts)
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


def _duplicate_support_context(
    citation_integrity_payload: dict[str, Any] | None,
    citation_review_payload: dict[str, Any] | None,
    *,
    limit: int = 16,
    examples_per_key: int = 4,
) -> list[dict[str, Any]]:
    if not isinstance(citation_integrity_payload, dict):
        return []
    checks = citation_integrity_payload.get("checks") if isinstance(citation_integrity_payload.get("checks"), dict) else {}
    duplicate = checks.get("duplicate_support") if isinstance(checks.get("duplicate_support"), dict) else {}
    duplicate_keys = [str(key).strip() for key in duplicate.get("duplicate_keys") or [] if str(key).strip()]
    if not duplicate_keys:
        return []
    review_items = citation_review_payload.get("items") if isinstance(citation_review_payload, dict) else []
    support_items = [item for item in review_items if isinstance(item, dict)] if isinstance(review_items, list) else []
    result: list[dict[str, Any]] = []
    for key in duplicate_keys:
        affected: list[dict[str, Any]] = []
        for index, item in enumerate(support_items, start=1):
            keys = {str(candidate).strip() for candidate in item.get("citation_keys") or [] if str(candidate).strip()}
            if key not in keys:
                continue
            affected.append(
                {
                    "id": str(item.get("id") or f"citation-support-{index}"),
                    "support_status": str(item.get("support_status") or item.get("status") or "unknown"),
                    "claim_type": item.get("claim_type"),
                    "risk": item.get("risk"),
                    "sentence": _truncate_context_text(item.get("sentence"), limit=900),
                }
            )
        result.append(
            {
                "issue_type": "citation_duplicate_support",
                "citation_key": key,
                "occurrence_count": len(affected) or None,
                "affected_items": affected[:examples_per_key],
                "suggested_fix": (
                    "Keep this citation only where it directly supports a distinct claim; "
                    "otherwise remove the repeated key, merge redundant support, or redistribute existing citations without adding bibliography keys."
                ),
            }
        )
        if len(result) >= limit:
            break
    return result


def _normalized_context_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _protected_citation_target_context(
    citation_review_payload: dict[str, Any] | None,
    citation_integrity_payload: dict[str, Any] | None,
) -> dict[str, set[str]]:
    """Return exact citation-repair targets that should not be protected.

    Weak/problematic citation support is placement-specific, especially for v3
    source-backed cases where one bibkey can support one anchor and fail
    another.  Therefore weak support contributes exact ids/texts only.  By
    contrast duplicate-support and citation-density repairs legitimately target
    any repeated/dense use of an affected key, so those contribute key-level
    exclusions.
    """

    problematic_statuses = {
        "weakly_supported",
        "unsupported",
        "contradicted",
        "insufficient_evidence",
        "needs_manual_check",
        "manual_check",
        "metadata_only",
        "evidence_missing",
        "weak",
        "fail",
        "human_needed",
    }
    ids: set[str] = set()
    texts: set[str] = set()
    key_exclusions: set[str] = set()
    if isinstance(citation_review_payload, dict):
        for item in citation_review_payload.get("items") or []:
            if not isinstance(item, dict):
                continue
            status = str(item.get("support_status") or item.get("status") or "").strip()
            if status not in problematic_statuses:
                continue
            item_id = str(item.get("id") or "").strip()
            if item_id:
                ids.add(item_id)
            sentence = _normalized_context_text(item.get("sentence"))
            if sentence:
                texts.add(sentence)
        for case in citation_review_payload.get("cases") or []:
            if not isinstance(case, dict):
                continue
            verdict = str(case.get("verdict") or case.get("support_status") or case.get("status") or "").strip()
            if verdict not in problematic_statuses:
                continue
            case_id = str(case.get("id") or "").strip()
            if case_id:
                ids.add(case_id)
            text = _normalized_context_text(case.get("anchor") or case.get("target"))
            if text:
                texts.add(text)

    checks = citation_integrity_payload.get("checks") if isinstance(citation_integrity_payload, dict) else {}
    checks = checks if isinstance(checks, dict) else {}
    duplicate = checks.get("duplicate_support") if isinstance(checks.get("duplicate_support"), dict) else {}
    key_exclusions.update(str(key).strip() for key in duplicate.get("duplicate_keys") or [] if str(key).strip())
    density = checks.get("citation_density") if isinstance(checks.get("citation_density"), dict) else {}
    for item in density.get("bomb_sentences") or []:
        if not isinstance(item, dict):
            continue
        key_exclusions.update(str(key).strip() for key in item.get("citation_keys") or [] if str(key).strip())
        sentence = _normalized_context_text(item.get("sentence"))
        if sentence:
            texts.add(sentence)
    for key_set in density.get("bomb_paragraph_key_sets") or []:
        if isinstance(key_set, list):
            key_exclusions.update(str(key).strip() for key in key_set if str(key).strip())
    return {"ids": ids, "texts": texts, "key_exclusions": key_exclusions}


def _protected_supported_citation_context(
    citation_review_payload: dict[str, Any] | None,
    citation_integrity_payload: dict[str, Any] | None,
    *,
    limit: int = 24,
) -> list[dict[str, Any]]:
    if not isinstance(citation_review_payload, dict):
        return []
    targets = _protected_citation_target_context(citation_review_payload, citation_integrity_payload)
    protected: list[dict[str, Any]] = []

    def _is_excluded(entry_id: str, text: str, keys: list[str]) -> bool:
        if entry_id and entry_id in targets["ids"]:
            return True
        normalized = _normalized_context_text(text)
        if normalized and normalized in targets["texts"]:
            return True
        return bool(set(keys) & targets["key_exclusions"])

    for item in citation_review_payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        status = str(item.get("support_status") or item.get("status") or "").strip()
        if status != "supported":
            continue
        sentence = _normalized_context_text(item.get("sentence"))
        keys = [str(key).strip() for key in item.get("citation_keys") or [] if str(key).strip()]
        entry_id = str(item.get("id") or "").strip()
        if not sentence or _is_excluded(entry_id, sentence, keys):
            continue
        protected.append(
            {
                "id": entry_id or f"supported-item-{len(protected) + 1}",
                "citation_keys": keys,
                "sentence": sentence,
                "source_shape": "items",
                "required_action": "preserve this already-supported citation-bearing sentence unless an active issue explicitly targets it",
            }
        )
        if len(protected) >= limit:
            return protected

    for case in citation_review_payload.get("cases") or []:
        if not isinstance(case, dict):
            continue
        verdict = str(case.get("verdict") or case.get("support_status") or case.get("status") or "").strip()
        if verdict not in {"pass", "supported"}:
            continue
        anchor = _normalized_context_text(case.get("anchor") or case.get("target"))
        keys = [str(case.get("key")).strip()] if str(case.get("key") or "").strip() else []
        entry_id = str(case.get("id") or "").strip()
        if not anchor or _is_excluded(entry_id, anchor, keys):
            continue
        protected.append(
            {
                "id": entry_id or f"supported-case-{len(protected) + 1}",
                "citation_keys": keys,
                "anchor": anchor,
                "source_shape": "cases",
                "required_action": "preserve this already-supported citation-bearing anchor unless an active issue explicitly targets it",
            }
        )
        if len(protected) >= limit:
            break
    return protected


def _protected_item_text(item: dict[str, Any]) -> str:
    return _normalized_context_text(item.get("sentence") or item.get("anchor"))


def _protected_supported_citation_regressions(
    imported: dict[str, Any],
    candidate_text: str,
    *,
    limit: int = 24,
) -> list[dict[str, Any]]:
    packet_path = imported.get("packet_path")
    if not packet_path:
        return []
    try:
        packet = _read_packet(packet_path)
    except Exception:
        return []
    citation_review = _packet_payload_by_role(packet, "citation_support_review")
    citation_integrity_audit = _packet_payload_by_role(packet, "citation_integrity_audit")
    protected = _protected_supported_citation_context(
        citation_review,
        citation_integrity_audit,
        limit=10_000,
    )
    if not isinstance(protected, list) or not protected:
        return []
    normalized_candidate = _normalized_context_text(candidate_text)
    regressions: list[dict[str, Any]] = []
    for item in protected:
        if not isinstance(item, dict):
            continue
        text = _protected_item_text(item)
        if not text or text in normalized_candidate:
            continue
        compact = {
            "id": str(item.get("id") or ""),
            "citation_keys": [str(key) for key in item.get("citation_keys") or [] if str(key).strip()],
        }
        if item.get("source_shape"):
            compact["source_shape"] = str(item.get("source_shape"))
        regressions.append(compact)
        if len(regressions) >= limit:
            break
    return regressions


def _operator_refinement_constraints(
    quality_eval_payload: dict[str, Any] | None,
    citation_integrity_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    before_failing_codes: list[str] = []
    if isinstance(quality_eval_payload, dict):
        tiers = quality_eval_payload.get("tiers") if isinstance(quality_eval_payload.get("tiers"), dict) else {}
        tier2 = tiers.get("tier_2_claim_safety") if isinstance(tiers.get("tier_2_claim_safety"), dict) else {}
        before_failing_codes.extend(str(code) for code in tier2.get("failing_codes") or [] if str(code).strip())
    if isinstance(citation_integrity_payload, dict):
        before_failing_codes.extend(str(code) for code in citation_integrity_payload.get("failing_codes") or [] if str(code).strip())
    before_failing_codes = sorted(dict.fromkeys(before_failing_codes))
    return {
        "before_failing_codes": before_failing_codes,
        "forbidden_new_tier2_codes": sorted(OPERATOR_REFINEMENT_FORBIDDEN_NEW_TIER2_CODES),
        "hard_constraints": [
            "Use only bibliography keys already present in citation_map.json; do not add new bibliography keys.",
            "Do not use dense citation bundles to hide weak support; split or role-clarify them when they obscure claim support.",
            "Do not introduce weak, unsupported, manual-check, metadata-only, or insufficient-evidence citation support.",
            "Do not introduce new high-risk uncited claims; scope, delete, or ground existing high-risk claims instead.",
            "Reduce duplicate-support and claim-support issues; never make their counts worse.",
        ],
    }


def _compact_metric_delta_records(records: Any, *, limit: int = 8) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if not isinstance(records, list):
        return result
    for record in records:
        if not isinstance(record, dict):
            continue
        compact = {
            "code": str(record.get("code") or ""),
            "before": record.get("before"),
            "after": record.get("after"),
            "delta": record.get("delta"),
        }
        if compact["code"]:
            result.append(compact)
        if len(result) >= limit:
            break
    return result


def _compact_prior_rejected_attempts(
    attempts: list[dict[str, Any]] | None,
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Return bounded code/count/hash-only memory for failed operator candidates.

    This memory is fed back into the next supervised operator attempt so the
    refiner can avoid repeating a repair shape that strict gates already
    rejected.  It intentionally omits candidate text, artifact paths, reviewer
    prose, and raw private source locations.
    """
    result: list[dict[str, Any]] = []
    for attempt in attempts or []:
        if not isinstance(attempt, dict):
            continue
        if attempt.get("gate_passed") is True:
            continue
        gate_reasons = sorted(dict.fromkeys(str(reason) for reason in attempt.get("gate_reasons") or [] if str(reason).strip()))
        if not gate_reasons:
            continue
        metric_delta = attempt.get("active_tier2_metric_delta") if isinstance(attempt.get("active_tier2_metric_delta"), dict) else {}
        compact: dict[str, Any] = {
            "attempt_index": attempt.get("attempt_index"),
            "candidate_sha256": str(attempt.get("candidate_sha256") or ""),
            "gate_reasons": gate_reasons,
            "resolved_active_failures": sorted(dict.fromkeys(str(code) for code in attempt.get("resolved_active_failures") or [] if str(code).strip())),
            "new_tier2_failures": sorted(dict.fromkeys(str(code) for code in attempt.get("new_tier2_failures") or [] if str(code).strip())),
            "candidate_active_failures": sorted(dict.fromkeys(str(code) for code in attempt.get("candidate_active_failures") or [] if str(code).strip())),
            "base_active_failures": sorted(dict.fromkeys(str(code) for code in attempt.get("base_active_failures") or [] if str(code).strip())),
        }
        if isinstance(metric_delta, dict):
            compact["metric_regressions"] = _compact_metric_delta_records(metric_delta.get("regressions"))
            compact["metric_improvements"] = _compact_metric_delta_records(metric_delta.get("improvements"))
            compact["base_total"] = metric_delta.get("base_total")
            compact["candidate_total"] = metric_delta.get("candidate_total")
        result.append(compact)
    return result[-limit:]


def _citation_density_context(payload: dict[str, Any] | None, *, limit: int = 16) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
    density = checks.get("citation_density") if isinstance(checks.get("citation_density"), dict) else {}
    result: list[dict[str, Any]] = []
    for item in density.get("bomb_sentences") or []:
        if not isinstance(item, dict):
            continue
        keys = [str(key) for key in item.get("citation_keys") or [] if str(key).strip()]
        result.append(
            {
                "issue_type": "citation_bomb_sentence",
                "id": item.get("id"),
                "sentence": _truncate_context_text(item.get("sentence"), limit=900),
                "citation_keys": keys,
                "citation_count": len(keys),
                "suggested_fix": "Split the sentence, remove redundant references, or scope the claim while preserving directly supporting citations.",
            }
        )
        if len(result) >= limit:
            return result
    for index, keys in enumerate(density.get("bomb_paragraph_key_sets") or [], start=1):
        if not isinstance(keys, list):
            continue
        normalized = [str(key) for key in keys if str(key).strip()]
        result.append(
            {
                "issue_type": "citation_bomb_paragraph",
                "id": f"citation-bomb-paragraph-{index}",
                "citation_keys": normalized,
                "citation_count": len(normalized),
                "suggested_fix": "Distribute citations across claim-specific sentences or remove redundant references.",
            }
        )
        if len(result) >= limit:
            break
    return result


def _figure_issue_context(payload: dict[str, Any] | None, *, limit: int = 12) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    result: list[dict[str, Any]] = []
    for item in payload.get("figures") or []:
        if not isinstance(item, dict):
            continue
        failing = [str(code) for code in item.get("failing_codes") or [] if str(code).strip()]
        warnings = [str(code) for code in item.get("warning_codes") or [] if str(code).strip()]
        if not failing and not warnings:
            continue
        result.append(
            {
                "issue_type": "figure_grounding",
                "label": str(item.get("label") or ""),
                "section_title": str(item.get("section_title") or ""),
                "failing_codes": failing,
                "warning_codes": warnings,
                "caption": _truncate_context_text(item.get("caption"), limit=500),
                "included_assets": [str(asset) for asset in item.get("included_assets") or [] if str(asset).strip()],
                "nearby_reference_context": _truncate_context_text(item.get("nearby_reference_context"), limit=500),
                "plot_manifest_match": item.get("plot_manifest_match")
                if isinstance(item.get("plot_manifest_match"), dict)
                else None,
                "suggested_fix": (
                    "Remove or quarantine nontechnical/decorative assets, replace placeholder or process captions "
                    "with scholarly figure content, and keep only figures that are referenced near the claims they support."
                ),
            }
        )
        if len(result) >= limit:
            break
    return result


def _operator_issue_context(imported: dict[str, Any], *, prior_attempts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
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
    citation_integrity_audit = _packet_payload_by_role(packet, "citation_integrity_audit")
    figure_placement_review = _packet_payload_by_role(packet, "figure_placement_review")
    prior_rejected_attempts = _compact_prior_rejected_attempts(prior_attempts)
    protected_supported = _protected_supported_citation_context(citation_review, citation_integrity_audit)
    context = {
        "problematic_citation_items": _problematic_citation_context(citation_review),
        "high_risk_uncited_claims": _high_risk_claim_context(quality_eval),
        "citation_density_issues": _citation_density_context(citation_integrity_audit),
        "citation_duplicate_support_issues": _duplicate_support_context(citation_integrity_audit, citation_review),
        "figure_placement_issues": _figure_issue_context(figure_placement_review),
        "refinement_constraints": _operator_refinement_constraints(quality_eval, citation_integrity_audit),
        "writer_instruction": (
            "Use these concrete sentences as the primary repair targets. Do not add new bibliography keys; "
            "either ground each sentence with existing directly supporting evidence, soften it into scoped author-material prose, or remove it. "
            "A candidate that uses dense citation bundles to hide weak support, weak citation support, duplicate support, or high-risk uncited claims will be rejected. "
            "Preserve protected_supported_citation_items exactly unless an active issue explicitly targets that item, anchor, sentence, or duplicate/density citation key."
        ),
    }
    if protected_supported:
        context["protected_supported_citation_items"] = protected_supported
    if prior_rejected_attempts:
        context["prior_rejected_attempts"] = prior_rejected_attempts
        context["prior_rejection_instruction"] = (
            "Do not repeat prior rejected repair shapes. If a prior attempt regressed active Tier-2 metrics, "
            "the next candidate must either reduce those active metrics without new regressions or leave the issue for human_needed."
        )
    return {key: value for key, value in context.items() if value}


def _write_operator_review_for_refiner(
    cwd: str | Path | None,
    imported: dict[str, Any],
    *,
    prior_attempts: list[dict[str, Any]] | None = None,
) -> Path:
    path = artifact_path(cwd, "operator_feedback.redacted_review.json")
    write_json(path, _operator_review_payload(imported, prior_attempts=prior_attempts))
    return path
