from __future__ import annotations

import re
from typing import Any

from paperorchestra.reviews.citation_source_fields import _clean_optional_string


def _source_locators(source: dict[str, Any]) -> list[str]:
    locators: list[str] = []
    arxiv = _clean_optional_string(source.get("arxiv"))
    if arxiv:
        arxiv_id = re.sub(r"(?i)^arxiv:\s*", "", arxiv).strip()
        arxiv_id = re.sub(r"v\d+$", "", arxiv_id)
        if arxiv_id:
            locators.append(f"https://arxiv.org/pdf/{arxiv_id}.pdf")
            locators.append(f"https://arxiv.org/abs/{arxiv_id}")
    url = _clean_optional_string(source.get("url"))
    if url:
        locators.append(url)
    doi = _clean_optional_string(source.get("doi"))
    if doi:
        doi_value = re.sub(r"(?i)^https?://(?:dx\.)?doi\.org/", "", doi).strip()
        if doi_value:
            locators.append(f"https://doi.org/{doi_value}")
    return list(dict.fromkeys(locators))
