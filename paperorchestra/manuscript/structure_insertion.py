from __future__ import annotations

import re

from paperorchestra.manuscript.structure_ranges import _section_range_map


def _paragraph_insertion_index(latex: str, start: int, section_end: int) -> int:
    paragraph_end = latex.find("\n\n", start, section_end)
    if paragraph_end != -1:
        return paragraph_end + 2
    line_end = latex.find("\n", start, section_end)
    if line_end != -1:
        return line_end + 1
    return section_end


def _preferred_section_name(
    latex: str,
    *,
    label: str | None = None,
    anchor_tokens: list[str] | None = None,
) -> str | None:
    ranges = _section_range_map(latex)
    if not ranges:
        return None
    if label:
        ref_match = re.search(rf"\\(?:eqref|ref)\{{{re.escape(label)}\}}", latex)
        if ref_match:
            for section_name, (start, end) in ranges.items():
                if start <= ref_match.start() < end:
                    return section_name
    lowered = latex.lower()
    for token in anchor_tokens or []:
        if not token:
            continue
        token_index = lowered.find(token.lower())
        if token_index == -1:
            continue
        for section_name, (start, end) in ranges.items():
            if start <= token_index < end:
                return section_name
    for preferred in ["method", "proposed method", "experiments", "implementation and results", "introduction", "related work", "background"]:
        if preferred in ranges:
            return preferred
    return next(iter(ranges))


def _insert_block_into_section(
    latex: str,
    *,
    section_name: str | None,
    block: str,
    label: str | None = None,
    anchor_tokens: list[str] | None = None,
) -> str:
    if not section_name:
        return latex + "\n" + block.strip() + "\n"
    ranges = _section_range_map(latex)
    target_range = ranges.get(section_name.strip().lower())
    if target_range is None:
        return latex + "\n" + block.strip() + "\n"
    start, end = target_range
    section_text = latex[start:end]
    if label:
        ref_match = re.search(rf"\\(?:eqref|ref)\{{{re.escape(label)}\}}", section_text)
        if ref_match:
            insert_at = _paragraph_insertion_index(latex, start + ref_match.end(), end)
            return latex[:insert_at] + "\n" + block.strip() + "\n" + latex[insert_at:]
    lowered_section = section_text.lower()
    for token in anchor_tokens or []:
        if not token:
            continue
        token_index = lowered_section.find(token.lower())
        if token_index == -1:
            continue
        insert_at = _paragraph_insertion_index(latex, start + token_index + len(token), end)
        return latex[:insert_at] + "\n" + block.strip() + "\n" + latex[insert_at:]
    return latex[:end] + "\n" + block.strip() + "\n" + latex[end:]
