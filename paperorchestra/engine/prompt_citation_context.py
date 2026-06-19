from __future__ import annotations

from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.manuscript.citation_key_parsing import CITE_COMMAND_RE
from paperorchestra.manuscript.citation_map_model import allowed_citation_keys

from .prompt_source_context import _source_grounding_text


def _unknown_citation_key_counts(latex: str, citation_map: dict[str, Any]) -> dict[str, int]:
    if not citation_map:
        return {}
    allowed = allowed_citation_keys(citation_map)
    counts: dict[str, int] = {}
    for match in CITE_COMMAND_RE.finditer(latex):
        for key in [key.strip() for key in match.group(2).split(",") if key.strip()]:
            if key not in allowed:
                counts[key] = counts.get(key, 0) + 1
    return counts


def _raise_if_strict_source_citations_unmapped(
    inputs: dict[str, str],
    citation_map: dict[str, Any],
    *,
    stage: str,
    strict_claim_safe: bool,
) -> None:
    if not strict_claim_safe:
        return
    unknown = _unknown_citation_key_counts(_source_grounding_text(inputs), citation_map)
    if not unknown:
        return
    detail = ", ".join(f"{key}({count})" for key, count in sorted(unknown.items()))
    raise ContractError(
        f"{stage} claim-safe source packet contains citation keys that are not present in citation_map.json: {detail}. "
        "Import/map these source citations into the verified citation registry before claim-safe writing."
    )
