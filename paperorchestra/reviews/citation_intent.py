from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import write_json
from paperorchestra.core.session import load_session
from paperorchestra.loop_engine.quality.utils import _file_sha256
from paperorchestra.reviews.citation_integrity_paths import citation_intent_plan_path
from paperorchestra.reviews.citation_integrity_support import (
    _cite_key_counts_from_text,
    _claim_map_by_key,
    _placement_roles,
    _role_tokens,
    _section_for_sentence,
    _support_items,
    _support_items_by_key,
    _support_items_by_sentence,
)
from paperorchestra.reviews.citation_rendered_references import _read_text


def build_citation_intent_plan(cwd: str | Path | None, *, quality_mode: str = "ralph") -> dict[str, Any]:
    """Build a non-generative map of where citations are being used.

    This is intentionally derived only from existing artifacts.  It does not
    invent missing citation intent; when richer claim/placement artifacts are
    absent it degrades to sentence-level records so a reviewer can still see
    what must be checked.
    """

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
