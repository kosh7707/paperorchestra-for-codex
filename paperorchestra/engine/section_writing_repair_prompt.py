from __future__ import annotations

import json
from typing import Any

from paperorchestra.engine.prompt_context import _data_block, _prompt_compact_text


def build_section_repair_retry_prompt(
    *,
    user_prompt: str,
    latex: str,
    blocking_issues: list[Any],
    min_citation_coverage: int,
) -> str:
    return f"""
{user_prompt}

{_data_block('current_draft.tex', _prompt_compact_text(latex, head_chars=10000, tail_chars=2000))}

{_data_block(
    'validation_issues.json',
    json.dumps([issue.to_dict() for issue in blocking_issues], indent=2, ensure_ascii=False),
)}

Repair Instructions:
- Revise the existing manuscript draft to satisfy the validation issues above.
- Use ONLY citation keys from the verified reference library.
- Increase citation coverage until the paper satisfies the citation coverage contract, using at least {min_citation_coverage} distinct verified citations when that many are available.
- Every decimal or percent value in the manuscript must appear verbatim in the measurement log. If a number is not grounded there, remove it or rewrite the claim qualitatively without introducing a replacement number.
- Ensure every required plot-plan figure is represented in the manuscript. Use available generated plot assets/snippets instead of inventing new figure files.
- Cover every required claim and narrative role item in its target section with meaningful, section-local prose rather than keyword stuffing.
- Expand every missing or shallow expected section with grounded, section-specific substance from the technical context, measurement log, section plan, and current template.
- Do not leave Method, Security Analysis, Implementation/Results, Discussion, or Conclusion as heading-only placeholders.
- Do not preserve input-note headings as manuscript sections; fold their constraints into Discussion and normal authorial prose.
- Preserve valid existing structure, plot usage, and grounded claims where possible.
- Do NOT invent meta sections such as checklists or workflow notes that are not part of the manuscript template.
- When rewrite_scope.json lists only_sections, preserve the existing section titles, citation keys, and figure references already present in current_template.tex.
- Return LaTeX only.
""".strip()
