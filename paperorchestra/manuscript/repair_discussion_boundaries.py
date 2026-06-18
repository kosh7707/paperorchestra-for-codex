from __future__ import annotations

import re
from typing import Any

from paperorchestra.manuscript import structure as _structure
from paperorchestra.manuscript.repair_claim_scope import _required_claim_scope_note


def _ensure_discussion_section_for_claim_boundaries(latex: str, claim_map: dict[str, Any] | None) -> str:
    claims = [
        claim
        for claim in (claim_map or {}).get("claims", [])
        if isinstance(claim, dict)
        and _structure._canonical_generated_section_title(str(claim.get("target_section") or "")) == "discussion"
        and claim.get("required", True)
    ]
    if not claims:
        return latex
    preferred_title = next(
        (str(claim.get("target_section") or "").strip() for claim in claims if str(claim.get("target_section") or "").strip()),
        "Discussion",
    )
    boundary_notes = []
    for claim in claims:
        note = _required_claim_scope_note(claim)
        if note and note not in boundary_notes:
            boundary_notes.append(note)
    if not boundary_notes:
        boundary_notes.append(
            "The paper's conclusions remain within the stated limitations, assumptions, and technical boundary and scope. "
            "This scope is part of the paper's stated technical model and does not extend beyond the presented assumptions, measurements, or evidence."
        )
    boundary_paragraph = "\n\n".join(boundary_notes) + "\n\n"
    ranges = _structure._normalized_section_range_map(latex)
    if "discussion" in ranges:
        start, end = ranges["discussion"]
        discussion_block = latex[start:end]
        if all(note in discussion_block for note in boundary_notes):
            return latex
        section_title_end = latex.find("}", start, end)
        insert_at = _structure._paragraph_insertion_index(latex, section_title_end + 1 if section_title_end != -1 else start, end)
        return latex[:insert_at] + "\n" + boundary_paragraph + latex[insert_at:]
    discussion = f"\\section{{{preferred_title}}}\n" + boundary_paragraph
    conclusion_match = re.search(r"\\section\{Conclusion\}", latex)
    if conclusion_match:
        return latex[: conclusion_match.start()] + discussion + latex[conclusion_match.start() :]
    end_index = latex.find("\\end{document}")
    if end_index != -1:
        return latex[:end_index] + discussion + latex[end_index:]
    return latex.rstrip() + "\n\n" + discussion
