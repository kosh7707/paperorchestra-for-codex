from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.quality.utils import _read_json_if_exists

_CITATION_REQUIRED_SOURCE_TYPES = {"external_literature", "standard", "benchmark_reference", "prior_work"}


def _claim_map_context_violations(state: Any) -> list[str]:
    payload = _read_json_if_exists(state.artifacts.claim_map_json)
    claims = payload.get("claims") if isinstance(payload, dict) else None
    if not isinstance(claims, list):
        return []
    violations: list[str] = []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_id = str(claim.get("id") or claim.get("claim_id") or "unknown")
        keys = [key for key in claim.get("citation_keys") or [] if str(key).strip()]
        if _own_contribution_has_citation(claim, keys):
            violations.append(claim_id)
            continue
        if _required_citation_is_missing(claim, keys):
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


def _own_contribution_has_citation(claim: dict[str, Any], keys: list[Any]) -> bool:
    claim_type = str(claim.get("claim_type") or "").strip().lower()
    return claim_type == "own_contribution" and bool(keys)


def _required_citation_is_missing(claim: dict[str, Any], keys: list[Any]) -> bool:
    required_source = str(claim.get("required_source_type") or "").strip().lower()
    explicit_required = claim.get("citation_required") is True or required_source in _CITATION_REQUIRED_SOURCE_TYPES
    return explicit_required and claim.get("required", True) is not False and not keys
