from __future__ import annotations


def _append_cross_artifact_issues(
    issues: list[str],
    *,
    registry_keys: set[str],
    registry_alias_keys: set[str],
    citation_map_keys: set[str],
    bib_keys: set[str],
    manuscript_citation_keys: set[str],
) -> None:
    if registry_keys and citation_map_keys:
        missing_from_map = sorted((registry_keys | registry_alias_keys) - citation_map_keys)
        allowed_map_keys = registry_keys | registry_alias_keys
        extra_in_map = sorted(citation_map_keys - allowed_map_keys)
        if missing_from_map:
            issues.append("citation_map.json is missing registry key(s): " + ", ".join(missing_from_map[:10]))
        if extra_in_map:
            issues.append("citation_map.json contains key(s) not present in citation_registry.json: " + ", ".join(extra_in_map[:10]))
    if registry_keys and bib_keys:
        missing_from_bib = sorted(registry_keys - bib_keys)
        extra_in_bib = sorted(bib_keys - registry_keys)
        if missing_from_bib:
            issues.append("references.bib is missing registry key(s): " + ", ".join(missing_from_bib[:10]))
        if extra_in_bib:
            issues.append("references.bib contains key(s) not present in citation_registry.json: " + ", ".join(extra_in_bib[:10]))
    if manuscript_citation_keys:
        if citation_map_keys:
            missing_from_map = sorted(manuscript_citation_keys - citation_map_keys)
            if missing_from_map:
                issues.append("manuscript cites key(s) missing from citation_map.json: " + ", ".join(missing_from_map[:10]))
        if bib_keys:
            missing_from_bib = sorted(manuscript_citation_keys - bib_keys)
            if missing_from_bib:
                issues.append("manuscript cites key(s) missing from references.bib: " + ", ".join(missing_from_bib[:10]))
