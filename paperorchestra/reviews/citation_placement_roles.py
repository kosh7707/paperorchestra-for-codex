from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.quality.utils import _read_json_if_exists
from paperorchestra.reviews.citation_integrity_helpers import _role_tokens


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
