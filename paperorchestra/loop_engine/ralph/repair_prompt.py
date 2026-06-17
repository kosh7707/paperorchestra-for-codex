from __future__ import annotations

import json
from typing import Any


def _repair_prompt(
    current_paper: str,
    citation_map: dict[str, Any],
    issues: list[dict[str, Any]],
    claim_safety_issues: list[dict[str, Any]] | None = None,
    source_obligation_context: dict[str, Any] | None = None,
) -> tuple[str, str]:
    system_prompt = """
You are a bounded PaperOrchestra citation-claim repair writer.
Revise only sentences listed in the citation or claim-safety issue packet.
Do not add new citations outside citation_map.json.
Do not add new empirical results, proof claims, or external facts.
Prefer softening, splitting, or removing unsupported cited claims, citation-dense sentences, redundant repeated citation support, and high-risk uncited claims.
Return the full revised LaTeX manuscript only.
""".strip()
    user_prompt = f"""
<DATA_BLOCK name="paper.tex">
{current_paper}
</DATA_BLOCK>

<DATA_BLOCK name="citation_map.json">
{json.dumps(citation_map, indent=2, ensure_ascii=False)}
</DATA_BLOCK>

<DATA_BLOCK name="citation_support_issues.json">
{json.dumps(issues, indent=2, ensure_ascii=False)}
</DATA_BLOCK>

<DATA_BLOCK name="claim_safety_repair_issues.json">
{json.dumps(claim_safety_issues or [], indent=2, ensure_ascii=False)}
</DATA_BLOCK>

<DATA_BLOCK name="source_obligations_context.json">
{json.dumps(source_obligation_context or {"available": False}, indent=2, ensure_ascii=False)}
</DATA_BLOCK>

Rules:
- Preserve unrelated sections.
- Preserve existing labels, figure paths, and bibliography hook.
- Use only citation keys already present in citation_map.json.
- Do not include reviewer numeric scores.
- Preserve author-material obligations in source_obligations_context.json. If a citation repair removes, weakens, or rewrites an author-material claim, keep the required terms/numeric tokens represented elsewhere with scoped wording instead of deleting the obligation silently.
- For citation-density issues, split dense citation bundles, remove redundant references, or place citations on the exact supported sentence.
- For duplicate-support issues, keep a repeated citation only where it directly supports a distinct claim; otherwise remove, redistribute, or merge the redundant support.
- For weakly_supported issues, apply the issue's suggested_fix narrowly. If the cited source supports only a weaker wording, rewrite the sentence to that weaker wording instead of adding citations.
- If a citation is attached to a paper-internal claim such as what this manuscript evaluates, instantiates, proves, or reports, remove the external citation from that internal claim unless citation_map evidence directly supports the external background portion.
- If an issue is only a bibliography-metadata correction and the cited evidence supports the sentence, do not change unrelated prose; leave bibliographic repair to the citation registry/metadata lane.
- For high-risk uncited claims, ground with existing verified evidence, scope as a limitation/author-material claim, or delete the claim.
""".strip()
    return system_prompt, user_prompt
