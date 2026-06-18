from __future__ import annotations

import re
from typing import Any

from paperorchestra.core.boundary import normalized_claim_projection
from paperorchestra.manuscript import structure as _structure
from paperorchestra.manuscript.citations import canonical_citation_key, canonical_citation_map, extract_citation_keys
from paperorchestra.manuscript.repair_text import _repair_inline_math_surplus_closing_brace, _sanitize_manuscript_control_prose


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


def _required_claim_scope_note(claim: dict[str, Any]) -> str:
    projection = normalized_claim_projection(claim)
    note = str(projection.get("scope_note") or "").strip()
    if not note:
        return ""
    if not note.endswith("."):
        note += "."
    return note + "\n\n"


def _ensure_required_claim_scope_notes(latex: str, claim_map: dict[str, Any] | None) -> str:
    if not isinstance(claim_map, dict):
        return _repair_inline_math_surplus_closing_brace(_sanitize_manuscript_control_prose(latex))
    rendered = _sanitize_manuscript_control_prose(latex)
    for claim in claim_map.get("claims") or []:
        if not isinstance(claim, dict) or not claim.get("required", True):
            continue
        note = _required_claim_scope_note(claim)
        if not note:
            continue
        target = _structure._canonical_generated_section_title(str(claim.get("target_section") or ""))
        ranges = _structure._normalized_section_range_map(rendered)
        if target not in ranges:
            continue
        start, end = ranges[target]
        section_block = rendered[start:end]
        if note.strip() in section_block:
            continue
        section_title_end = rendered.find("}", start, end)
        insert_at = _structure._paragraph_insertion_index(rendered, section_title_end + 1 if section_title_end != -1 else start, end)
        rendered = rendered[:insert_at] + "\n" + note + rendered[insert_at:]
    return _repair_inline_math_surplus_closing_brace(rendered)


def _citation_map_for_selected_sections(source_latex: str, citation_map: dict[str, Any], selected_sections: list[str]) -> dict[str, Any]:
    if not citation_map:
        return {}
    ranges = _structure._section_range_map(source_latex)
    selected_keys: set[str] = set()
    for section_name in selected_sections:
        section_range = ranges.get(section_name.strip().lower())
        if section_range is None:
            continue
        block = source_latex[section_range[0] : section_range[1]]
        selected_keys.update(extract_citation_keys(block))
    if not selected_keys:
        return canonical_citation_map(citation_map)
    canonical_selected = {canonical_citation_key(key, citation_map) for key in selected_keys if key in citation_map}
    subset = {key: value for key, value in canonical_citation_map(citation_map).items() if key in canonical_selected}
    return subset or canonical_citation_map(citation_map)
