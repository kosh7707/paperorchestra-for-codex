from __future__ import annotations

from typing import Any

from paperorchestra.manuscript.narrative_contracts import (
    CITATION_PLACEMENT_PLAN_SCHEMA_VERSION,
    CLAIM_MAP_SCHEMA_VERSION,
)


def build_claim_map(*, claims: list[dict[str, Any]], source_hashes: dict[str, str | None]) -> dict[str, Any]:
    return {
        "schema_version": CLAIM_MAP_SCHEMA_VERSION,
        "source_hashes": source_hashes,
        "claims": claims,
    }


def build_citation_plan(*, claims: list[dict[str, Any]], source_hashes: dict[str, str | None]) -> dict[str, Any]:
    return {
        "schema_version": CITATION_PLACEMENT_PLAN_SCHEMA_VERSION,
        "source_hashes": source_hashes,
        "placements": citation_placements(claims),
    }


def citation_placements(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "claim_id": claim["id"],
            "target_section": claim["target_section"],
            "citation_keys": claim["citation_keys"],
            "support_role": "background" if claim["claim_type"] == "positioning" else "contrast",
            "placement_rule": "same_sentence_or_adjacent",
        }
        for claim in claims
        if claim.get("citation_keys")
    ]
