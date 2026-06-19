from __future__ import annotations

from paperorchestra.manuscript.structure import SECTION_COMMAND_RE, _canonical_generated_section_title, _normalized_section_range_map, _section_range_map


def _section_range_for_name(latex: str, section_name: str) -> tuple[int, int] | None:
    raw_ranges = _section_range_map(latex)
    raw_key = section_name.strip().lower()
    if raw_key in raw_ranges:
        return raw_ranges[raw_key]
    return _normalized_section_range_map(latex).get(_canonical_generated_section_title(section_name))


def _preserve_existing_sections(generated_latex: str, source_latex: str, *, section_names: list[str]) -> str:
    merged = generated_latex
    for section_name in section_names:
        source_range = _section_range_for_name(source_latex, section_name)
        if source_range is None:
            continue
        target_range = _section_range_for_name(merged, section_name)
        if target_range is None:
            continue
        source_block = source_latex[source_range[0] : source_range[1]]
        merged = merged[: target_range[0]] + source_block + merged[target_range[1] :]
    return merged


def _preserve_all_except_sections(generated_latex: str, source_latex: str, *, rewritten_section_names: list[str]) -> str:
    rewritten = {_canonical_generated_section_title(name) for name in rewritten_section_names if name and name.strip()}
    protected_names = [
        section_name
        for section_name in _section_range_map(source_latex)
        if _canonical_generated_section_title(section_name) not in rewritten
    ]
    return _preserve_existing_sections(generated_latex, source_latex, section_names=protected_names)


def _selected_section_template(source_latex: str, selected_sections: list[str]) -> str:
    ranges = _section_range_map(source_latex)
    matches = list(SECTION_COMMAND_RE.finditer(source_latex))
    preamble_end = matches[0].start() if matches else source_latex.find("\\begin{document}")
    if preamble_end == -1:
        preamble_end = 0
    preamble = source_latex[:preamble_end]
    blocks: list[str] = []
    for section_name in selected_sections:
        section_range = ranges.get(section_name.strip().lower()) or _section_range_for_name(source_latex, section_name)
        if section_range is None:
            continue
        blocks.append(source_latex[section_range[0] : section_range[1]])
    end_document = "\\end{document}\n" if "\\end{document}" in source_latex else ""
    return preamble + "".join(blocks) + end_document
