from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from paperorchestra.core.io import write_json
from paperorchestra.loop_engine.quality.utils import _file_sha256, _read_json_if_exists
from paperorchestra.manuscript.validator import extract_citation_keys
from paperorchestra.reviews.citation_integrity_gate import (
    build_citation_integrity_critic,
    citation_integrity_check,
    write_citation_integrity_critic,
)
from paperorchestra.reviews.citation_integrity_paths import (
    CITATION_INTEGRITY_AUDIT_FILENAME,
    CITATION_INTEGRITY_CRITIC_FILENAME,
    CITATION_INTENT_PLAN_FILENAME,
    CITATION_SOURCE_MATCH_FILENAME,
    citation_integrity_audit_path,
    citation_integrity_critic_path,
    citation_intent_plan_path,
    citation_source_match_path,
)
from paperorchestra.reviews.citation_integrity_support import (
    _citation_support_review_path,
    _cite_key_counts_from_text,
    _claim_map_by_key,
    _claim_map_context_violations,
    _duplicate_support_failures,
    _placement_roles,
    _role_tokens,
    _section_for_sentence,
    _status_counts,
    _support_items,
    _support_items_by_key,
    _support_items_by_sentence,
    _support_items_from_v3_cases,
    _v3_evidence_text_readable,
    _v3_support_status,
)
from paperorchestra.reviews.citation_rendered_references import (
    rendered_reference_audit_path,
    _duplicate_reference_identity_groups,
    _read_text,
    _reference_identity_label,
    build_rendered_reference_audit,
    write_rendered_reference_audit,
)


def build_citation_intent_plan(cwd: str | Path | None, *, quality_mode: str = "ralph") -> dict[str, Any]:
    """Build a non-generative map of where citations are being used.

    This is intentionally derived only from existing artifacts.  It does not
    invent missing citation intent; when richer claim/placement artifacts are
    absent it degrades to sentence-level records so a reviewer can still see
    what must be checked.
    """

    from paperorchestra.core.session import load_session

    state = load_session(cwd)
    latex = _read_text(state.artifacts.paper_full_tex)
    manuscript_sha = _file_sha256(state.artifacts.paper_full_tex)
    sentence_records, _ = _cite_key_counts_from_text(latex)
    claim_by_key = _claim_map_by_key(state)
    support_by_sentence = _support_items_by_sentence(_support_items(cwd, state))
    support_by_key = _support_items_by_key(_support_items(cwd, state))
    placement_roles = _placement_roles(state)
    intent_items: list[dict[str, Any]] = []
    degraded = not state.artifacts.claim_map_json and not state.artifacts.citation_placement_plan_json
    for record in sentence_records:
        keys = [str(key) for key in record.get("citation_keys") or []]
        sentence = str(record.get("sentence") or "")
        matching_support = support_by_sentence.get(sentence, [])
        claim_ids: list[str] = []
        required_source_types: set[str] = set()
        roles: set[str] = set()
        for key in keys:
            for claim in claim_by_key.get(key, []):
                claim_id = claim.get("id") or claim.get("claim_id")
                if claim_id:
                    claim_ids.append(str(claim_id))
                required = claim.get("required_source_type") or claim.get("source_type")
                if required:
                    required_source_types.add(str(required))
            roles.update(placement_roles.get(key, set()))
            for item in support_by_key.get(key, []):
                for field in ["claim_type", "citation_role", "support_role"]:
                    roles.update(_role_tokens(item.get(field)))
        for item in matching_support:
            for field in ["claim_id", "claim_ids", "claim_type", "citation_role", "support_role"]:
                roles.update(_role_tokens(item.get(field)))
        intent_items.append(
            {
                "id": record.get("id"),
                "sentence": sentence,
                "section": _section_for_sentence(latex, sentence),
                "citation_keys": keys,
                "citation_needed": True,
                "claim_ids": sorted(dict.fromkeys(claim_ids)),
                "citation_roles": sorted(role for role in roles if role),
                "required_source_types": sorted(required_source_types),
                "support_review_item_count": len(matching_support),
                "rationale": "derived_from_existing_claim_and_support_artifacts"
                if (claim_ids or roles or matching_support)
                else "degraded_sentence_level_record_no_claim_intent_artifact",
            }
        )
    return {
        "schema_version": "citation-intent-plan/1",
        "status": "pass" if intent_items else "skipped",
        "quality_mode": quality_mode,
        "manuscript_sha256": manuscript_sha,
        "paper_full_tex_sha256": manuscript_sha,
        "degraded": degraded,
        "citation_sentence_count": len(intent_items),
        "items": intent_items,
        "failing_codes": [],
    }


def write_citation_intent_plan(
    cwd: str | Path | None,
    *,
    quality_mode: str = "ralph",
    output_path: str | Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    payload = build_citation_intent_plan(cwd, quality_mode=quality_mode)
    path = Path(output_path).resolve() if output_path else citation_intent_plan_path(cwd)
    write_json(path, payload)
    return path, payload


def build_citation_source_match(cwd: str | Path | None, *, quality_mode: str = "ralph") -> dict[str, Any]:
    """Bind the citation support review into an explicit source-match artifact."""

    from paperorchestra.core.session import load_session

    state = load_session(cwd)
    support_path = _citation_support_review_path(cwd, state)
    support = _read_json_if_exists(support_path)
    manuscript_sha = _file_sha256(state.artifacts.paper_full_tex)
    if not isinstance(support, dict):
        return {
            "schema_version": "citation-source-match/1",
            "status": "skipped",
            "quality_mode": quality_mode,
            "manuscript_sha256": manuscript_sha,
            "paper_full_tex_sha256": manuscript_sha,
            "citation_support_review": str(support_path),
            "citation_support_review_sha256": None,
            "reason": "citation_support_review_missing_or_unreadable",
            "items": [],
            "support_status_counts": {},
            "failing_codes": [],
        }
    items = _support_items(cwd, state)
    match_items: list[dict[str, Any]] = []
    failing_statuses = {"unsupported", "contradicted"}
    if quality_mode == "claim_safe":
        failing_statuses.update({"metadata_only", "insufficient_evidence"})
    for index, item in enumerate(items, start=1):
        status = str(item.get("support_status") or "unknown").strip().lower() or "unknown"
        evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
        match_items.append(
            {
                "id": str(item.get("id") or f"citation-support-{index}"),
                "sentence": item.get("sentence"),
                "citation_keys": [str(key) for key in item.get("citation_keys") or []],
                "support_status": status,
                "claim_type": item.get("claim_type"),
                "evidence_mode": support.get("evidence_mode"),
                "source_match_status": "fail" if status in failing_statuses else "pass",
                "evidence_count": len(evidence),
                "rationale": item.get("rationale") or item.get("reason") or item.get("explanation"),
            }
        )
    mismatch_ids = [str(item.get("id")) for item in match_items if item.get("source_match_status") == "fail"]
    failing = ["claim_source_mismatch"] if mismatch_ids else []
    return {
        "schema_version": "citation-source-match/1",
        "status": "fail" if mismatch_ids else "pass",
        "quality_mode": quality_mode,
        "manuscript_sha256": manuscript_sha,
        "paper_full_tex_sha256": manuscript_sha,
        "citation_support_review": str(support_path),
        "citation_support_review_sha256": _file_sha256(support_path),
        "evidence_mode": support.get("evidence_mode"),
        "support_status_counts": _status_counts(items),
        "failing_statuses": sorted(failing_statuses),
        "mismatch_item_ids": mismatch_ids,
        "items": match_items,
        "failing_codes": failing,
    }


def write_citation_source_match(
    cwd: str | Path | None,
    *,
    quality_mode: str = "ralph",
    output_path: str | Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    payload = build_citation_source_match(cwd, quality_mode=quality_mode)
    path = Path(output_path).resolve() if output_path else citation_source_match_path(cwd)
    write_json(path, payload)
    return path, payload


def build_citation_integrity_audit(cwd: str | Path | None, *, quality_mode: str = "ralph") -> dict[str, Any]:
    from paperorchestra.core.session import load_session

    state = load_session(cwd)
    manuscript_sha = _file_sha256(state.artifacts.paper_full_tex)
    latex = _read_text(state.artifacts.paper_full_tex)
    sentence_records, text_counts = _cite_key_counts_from_text(latex)
    items = _support_items(cwd, state)
    placement_roles = _placement_roles(state)
    citation_bomb_sentences = [record for record in sentence_records if len(record.get("citation_keys") or []) > 3]
    paragraph_keys = [sorted(extract_citation_keys(paragraph)) for paragraph in re.split(r"\n\s*\n", latex)]
    citation_bomb_paragraphs = [keys for keys in paragraph_keys if len(keys) > 5]
    duplicate_keys = _duplicate_support_failures(items, text_counts, placement_roles)
    mismatch_statuses = {"unsupported", "contradicted"}
    if quality_mode == "claim_safe":
        mismatch_statuses.update({"metadata_only", "insufficient_evidence"})
    mismatch_items = [
        item for item in items if str(item.get("support_status") or "").strip().lower() in mismatch_statuses
    ]
    context_violations = _claim_map_context_violations(state)
    failing: list[str] = []
    warnings: list[str] = []
    if citation_bomb_sentences or citation_bomb_paragraphs:
        warnings.append("dense_citation_bundle_requires_role_check")
    if duplicate_keys:
        failing.append("citation_duplicate_support")
    if mismatch_items:
        failing.append("claim_source_mismatch")
    if context_violations:
        failing.append("citation_context_policy_violation")
    intent_path = citation_intent_plan_path(cwd)
    source_match_path = citation_source_match_path(cwd)
    rendered_path = rendered_reference_audit_path(cwd)
    support_path = _citation_support_review_path(cwd, state)
    return {
        "schema_version": "citation-integrity-audit/1",
        "status": "fail" if failing else "warn" if warnings else "pass",
        "manuscript_sha256": manuscript_sha,
        "paper_full_tex_sha256": manuscript_sha,
        "failing_codes": sorted(dict.fromkeys(failing)),
        "warning_codes": sorted(dict.fromkeys(warnings)),
        "source_artifacts": {
            "citation_intent_plan": str(intent_path),
            "citation_intent_plan_sha256": _file_sha256(intent_path),
            "citation_source_match": str(source_match_path),
            "citation_source_match_sha256": _file_sha256(source_match_path),
            "citation_support_review": str(support_path),
            "citation_support_review_sha256": _file_sha256(support_path),
            "rendered_reference_audit": str(rendered_path),
            "rendered_reference_audit_sha256": _file_sha256(rendered_path),
        },
        "checks": {
            "citation_density": {
                "status": "warn" if citation_bomb_sentences or citation_bomb_paragraphs else "pass",
                "bomb_sentences": citation_bomb_sentences,
                "bomb_paragraph_key_sets": citation_bomb_paragraphs,
                "max_keys_per_sentence": 3,
                "max_keys_per_paragraph": 5,
                "warning_codes": ["dense_citation_bundle_requires_role_check"]
                if citation_bomb_sentences or citation_bomb_paragraphs
                else [],
            },
            "duplicate_support": {
                "status": "fail" if duplicate_keys else "pass",
                "duplicate_keys": duplicate_keys,
                "threshold_repeated_sentences": 3,
                "min_distinct_role_or_claim_count": 2,
            },
            "claim_source_match": {
                "status": "fail" if mismatch_items else "pass",
                "mismatch_item_ids": [
                    str(item.get("id") or item.get("sentence") or "unknown")
                    for item in mismatch_items
                ],
                "failing_statuses": sorted(mismatch_statuses),
            },
            "context_policy": {
                "status": "fail" if context_violations else "pass",
                "violating_claim_ids": context_violations,
            },
        },
    }


def write_citation_integrity_audit(
    cwd: str | Path | None,
    *,
    quality_mode: str = "ralph",
    output_path: str | Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    write_citation_intent_plan(cwd, quality_mode=quality_mode)
    write_citation_source_match(cwd, quality_mode=quality_mode)
    payload = build_citation_integrity_audit(cwd, quality_mode=quality_mode)
    path = citation_integrity_audit_path(cwd)
    write_json(path, payload)
    if output_path:
        extra_path = Path(output_path).resolve()
        if extra_path != path:
            write_json(extra_path, payload)
            return extra_path, payload
    return path, payload
