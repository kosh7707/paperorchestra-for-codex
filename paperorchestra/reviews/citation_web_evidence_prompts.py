from __future__ import annotations

import hashlib
import json
from typing import Any


def _web_evidence_prompts(items: list[dict[str, Any]]) -> tuple[str, str]:
    review_items = [
        {
            "id": item["id"],
            "sentence": item["sentence"],
            "citation_keys": item["citation_keys"],
            "citation_entries": item["citation_entries"],
            "claim_type": item["claim_type"],
        }
        for item in items
    ]
    system_prompt = """
You are PaperOrchestra's citation-support evidence retriever.
Your job is to collect source evidence only, before any verdict is assigned.

Rules:
- Use web/source lookup if available.
- Do not decide final support_status.
- Do not rewrite manuscript prose.
- Do not invent bibliographic metadata, URLs, source titles, or evidence.
- Return JSON only.
""".strip()
    user_prompt = f"""
Collect cited-source evidence for these manuscript sentences.

Return JSON with exactly these top-level keys:
- items: array, one object per input id
- research_notes: array of strings

Each item must contain:
- id
- evidence: array of objects with citation_key, source_title, url, evidence_quote_or_summary, supports_claim

Input:
{json.dumps({"items": review_items}, indent=2, ensure_ascii=False)}
""".strip()
    return system_prompt, user_prompt


def _trace_base(system_prompt: str, user_prompt: str, response: str) -> dict[str, Any]:
    return {
        "schema_version": "citation-support-retrieval-trace/1",
        "system_prompt_sha256": hashlib.sha256(system_prompt.encode("utf-8")).hexdigest(),
        "user_prompt_sha256": hashlib.sha256(user_prompt.encode("utf-8")).hexdigest(),
        "response_sha256": hashlib.sha256(response.encode("utf-8")).hexdigest(),
        "web_search_required": True,
    }
