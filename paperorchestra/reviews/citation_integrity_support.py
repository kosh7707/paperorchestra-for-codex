from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.session import artifact_path
from paperorchestra.loop_engine.quality.utils import _read_json_if_exists
from paperorchestra.reviews.citation_integrity_helpers import (
    _cite_key_counts_from_text,
    _duplicate_support_failures,
    _role_tokens,
    _section_for_sentence,
    _sentences_with_cites,
    _status_counts,
    _support_items_by_key,
    _support_items_by_sentence,
)
from paperorchestra.reviews.citation_support_v3 import _support_items_from_v3_cases


def _citation_support_review_path(cwd: str | Path | None, state: Any) -> Path:
    if state.artifacts.paper_full_tex:
        return Path(state.artifacts.paper_full_tex).resolve().parent / "citation_support_review.json"
    return artifact_path(cwd, "citation_support_review.json")


def _support_items(cwd: str | Path | None, state: Any) -> list[dict[str, Any]]:
    support_path = _citation_support_review_path(cwd, state)
    payload = _read_json_if_exists(support_path)
    if isinstance(payload, dict) and payload.get("schema") == "citation-support-review/3":
        return _support_items_from_v3_cases(payload.get("cases"), run_root=support_path.parent.parent)
    items = payload.get("items") if isinstance(payload, dict) else None
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _placement_roles(state: Any) -> dict[str, set[str]]:
    payload = _read_json_if_exists(state.artifacts.citation_placement_plan_json)
    placements = payload.get("placements") if isinstance(payload, dict) else None
    result: dict[str, set[str]] = {}
    if not isinstance(placements, list):
        return result
    for item in placements:
        if not isinstance(item, dict):
            continue
        keys = []
        for key_field in ["citation_key", "key"]:
            if item.get(key_field):
                keys.append(str(item.get(key_field)))
        keys.extend(str(key) for key in item.get("citation_keys") or [])
        roles = set()
        for field in ["claim_id", "claim_ids", "citation_role", "citation_roles", "support_role"]:
            roles.update(_role_tokens(item.get(field)))
        for key in keys:
            result.setdefault(key, set()).update(roles)
    return result


def _claim_map_context_violations(state: Any) -> list[str]:
    payload = _read_json_if_exists(state.artifacts.claim_map_json)
    claims = payload.get("claims") if isinstance(payload, dict) else None
    if not isinstance(claims, list):
        return []
    violations: list[str] = []
    citation_required_types = {"external_literature", "standard", "benchmark_reference", "prior_work"}
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_id = str(claim.get("id") or claim.get("claim_id") or "unknown")
        claim_type = str(claim.get("claim_type") or "").strip().lower()
        keys = [key for key in claim.get("citation_keys") or [] if str(key).strip()]
        if claim_type == "own_contribution" and keys:
            violations.append(claim_id)
            continue
        required_source = str(claim.get("required_source_type") or "").strip().lower()
        explicit_required = claim.get("citation_required") is True or required_source in citation_required_types
        if explicit_required and claim.get("required", True) is not False and not keys:
            violations.append(claim_id)
    return sorted(violations)


def _claim_map_by_key(state: Any) -> dict[str, list[dict[str, Any]]]:
    payload = _read_json_if_exists(state.artifacts.claim_map_json)
    claims = payload.get("claims") if isinstance(payload, dict) else None
    result: dict[str, list[dict[str, Any]]] = {}
    if not isinstance(claims, list):
        return result
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        for key in claim.get("citation_keys") or []:
            normalized = str(key).strip()
            if normalized:
                result.setdefault(normalized, []).append(claim)
    return result
