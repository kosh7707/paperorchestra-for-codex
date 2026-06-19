from __future__ import annotations

import json

from paperorchestra.domains import get_domain


def build_prior_work_seed_response() -> str:
    return json.dumps(
        {
            "references": [dict(item) for item in get_domain().mock_prior_work_references],
            "research_notes": ["Mock provider returns canonical seed examples without live web access."],
        },
        indent=2,
    )
