from __future__ import annotations

from typing import Any

from paperorchestra.reviews.citation_quality_tokens import _tokens


def _claims_by_key(payload: Any) -> dict[str, list[dict[str, Any]]]:
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


def _roles_by_key(payload: Any) -> dict[str, set[str]]:
    placements = payload.get("placements") if isinstance(payload, dict) else None
    result: dict[str, set[str]] = {}
    if not isinstance(placements, list):
        return result
    for item in placements:
        if not isinstance(item, dict):
            continue
        keys = [str(item.get(field)).strip() for field in ("citation_key", "key") if item.get(field)]
        keys.extend(str(key).strip() for key in item.get("citation_keys") or [] if str(key).strip())
        roles: set[str] = set()
        for field in ("claim_id", "claim_ids", "citation_role", "citation_roles", "support_role", "claim_type", "criticality"):
            roles.update(_tokens(item.get(field)))
        for key in keys:
            result.setdefault(key, set()).update(roles)
    return result
