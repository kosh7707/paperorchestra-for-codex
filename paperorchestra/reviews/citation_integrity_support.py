from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from paperorchestra.core.session import artifact_path
from paperorchestra.loop_engine.quality.utils import _read_json_if_exists
from paperorchestra.manuscript.citations import extract_citation_keys
from paperorchestra.reviews.citation_support_v3 import _support_items_from_v3_cases


def _citation_support_review_path(cwd: str | Path | None, state: Any) -> Path:
    if state.artifacts.paper_full_tex:
        return Path(state.artifacts.paper_full_tex).resolve().parent / "citation_support_review.json"
    return artifact_path(cwd, "citation_support_review.json")


def _sentences_with_cites(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", text) if "\\cite" in part]


def _cite_key_counts_from_text(text: str) -> tuple[list[dict[str, Any]], dict[str, int]]:
    sentences = _sentences_with_cites(text)
    records: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for idx, sentence in enumerate(sentences, start=1):
        keys = sorted(extract_citation_keys(sentence))
        records.append({"id": f"tex-sentence-{idx}", "sentence": sentence, "citation_keys": keys})
        for key in keys:
            counts[key] = counts.get(key, 0) + 1
    return records, counts


def _support_items(cwd: str | Path | None, state: Any) -> list[dict[str, Any]]:
    support_path = _citation_support_review_path(cwd, state)
    payload = _read_json_if_exists(support_path)
    if isinstance(payload, dict) and payload.get("schema") == "citation-support-review/3":
        return _support_items_from_v3_cases(payload.get("cases"), run_root=support_path.parent.parent)
    items = payload.get("items") if isinstance(payload, dict) else None
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []



def _role_tokens(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, list):
        return {str(item).strip() for item in value if str(item).strip()}
    return {str(value).strip()} if str(value).strip() else set()


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


def _duplicate_support_failures(
    items: list[dict[str, Any]],
    text_counts: dict[str, int],
    placement_roles: dict[str, set[str]],
) -> list[str]:
    counts = dict(text_counts)
    roles_by_key: dict[str, set[str]] = {
        key: set(value) for key, value in placement_roles.items()
    }
    if items:
        counts = {}
        for item in items:
            keys = [str(key) for key in item.get("citation_keys") or []]
            item_roles = set()
            for field in ["claim_id", "claim_ids", "citation_role", "citation_roles", "support_role"]:
                item_roles.update(_role_tokens(item.get(field)))
            for key in keys:
                counts[key] = counts.get(key, 0) + 1
                roles_by_key.setdefault(key, set()).update(item_roles)
    return sorted(
        key for key, count in counts.items()
        if count > 3 and len(roles_by_key.get(key, set())) < 2
    )


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


def _section_for_sentence(latex: str, sentence: str) -> str | None:
    needle = sentence[:80]
    idx = latex.find(needle) if needle else -1
    if idx < 0:
        idx = latex.find(sentence[:30]) if sentence else -1
    before = latex[:idx] if idx >= 0 else latex
    sections = re.findall(r"\\(?:sub)*section\*?\{([^}]+)\}", before)
    return sections[-1].strip() if sections else None

def _support_items_by_sentence(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        sentence = str(item.get("sentence") or "").strip()
        if sentence:
            result.setdefault(sentence, []).append(item)
    return result

def _support_items_by_key(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        for key in item.get("citation_keys") or []:
            normalized = str(key).strip()
            if normalized:
                result.setdefault(normalized, []).append(item)
    return result


def _status_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        status = str(item.get("support_status") or "unknown").strip().lower() or "unknown"
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))
