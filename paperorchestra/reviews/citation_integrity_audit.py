from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from paperorchestra.core.io import write_json
from paperorchestra.core.session import load_session
from paperorchestra.loop_engine.quality.utils import _file_sha256
from paperorchestra.manuscript.citations import extract_citation_keys
from paperorchestra.reviews.citation_integrity_paths import (
    citation_integrity_audit_path,
    citation_intent_plan_path,
    citation_source_match_path,
)
from paperorchestra.reviews.citation_claim_context import _claim_map_context_violations
from paperorchestra.reviews.citation_integrity_helpers import _cite_key_counts_from_text, _duplicate_support_failures
from paperorchestra.reviews.citation_placement_roles import _placement_roles
from paperorchestra.reviews.citation_support_items import _citation_support_review_path, _support_items
from paperorchestra.reviews.citation_intent import write_citation_intent_plan
from paperorchestra.reviews.citation_rendered_references import _read_text, rendered_reference_audit_path
from paperorchestra.reviews.citation_source_match import write_citation_source_match


def build_citation_integrity_audit(cwd: str | Path | None, *, quality_mode: str = "ralph") -> dict[str, Any]:
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
