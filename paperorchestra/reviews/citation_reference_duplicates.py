from __future__ import annotations

from typing import Any

from paperorchestra.reviews.citation_reference_normalizers import _reference_identity_label


def _duplicate_reference_identity_groups(visible_keys: list[str], entries: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    by_identity: dict[str, list[str]] = {}
    for key in visible_keys:
        entry = entries.get(key)
        if not entry:
            continue
        identity = _reference_identity_label(entry)
        if not identity:
            continue
        by_identity.setdefault(identity, []).append(key)
    groups = [
        {"identity": identity, "keys": sorted(dict.fromkeys(keys))}
        for identity, keys in by_identity.items()
        if len(set(keys)) > 1
    ]
    return sorted(groups, key=lambda group: (str(group["identity"]), list(group["keys"])))
