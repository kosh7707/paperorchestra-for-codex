from __future__ import annotations

import json
import re

from paperorchestra.runtime.provider_base import CompletionRequest


def build_citation_support_response(request: CompletionRequest) -> str:
    ids = re.findall(r'"id"\s*:\s*"(cite-\d+)"', request.user_prompt)
    return json.dumps(
        {
            "items": [
                {
                    "id": item_id,
                    "support_status": "needs_manual_check",
                    "risk": "medium",
                    "claim_type": "background",
                    "evidence": [],
                    "reasoning": "Mock provider cannot perform live web/source inspection.",
                    "suggested_fix": "Run a web-search-capable provider or manually verify this cited sentence.",
                }
                for item_id in ids
            ],
            "research_notes": ["Mock provider does not claim cited-sentence support."],
        },
        indent=2,
    )
