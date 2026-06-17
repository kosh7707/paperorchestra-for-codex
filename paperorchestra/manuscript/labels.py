from __future__ import annotations

import re

from paperorchestra.manuscript.structure import (
    LABEL_RE,
    SECTION_COMMAND_RE,
    SUBSECTION_COMMAND_RE,
    _insert_block_into_section,
    _preferred_section_name,
    _section_range_map,
)


COMMON_GENERATED_SECTION_LABELS: dict[str, tuple[str, ...]] = {
    "sec:intro": ("introduction",),
    "sec:related": ("background and related work", "related work", "background"),
    "sec:background": ("background and related work", "background", "related work"),
    "sec:method": (
        "method",
        "methodology",
        "proposed method",
        "construction",
    ),
    "sec:construction": (
        "method",
        "methodology",
        "proposed method",
        "construction",
    ),
    "sec:security": ("security analysis", "security proof", "analysis"),
    "sec:impl": (
        "implementation and results",
        "implementation results",
        "implementation",
        "experiments",
        "evaluation",
    ),
    "sec:results": (
        "implementation and results",
        "implementation results",
        "results",
        "experiments",
        "evaluation",
    ),
    "sec:discussion": ("discussion and limitations", "discussion", "limitations"),
    "sec:conclusion": ("conclusion",),
}


def _restore_missing_referenced_labels(generated_latex: str, template_latex: str) -> str:
    referenced_labels = set(re.findall(r"\\(?:eqref|ref)\{([^}]+)\}", generated_latex))
    if not referenced_labels:
        return generated_latex
    existing_labels = set(LABEL_RE.findall(generated_latex))
    missing = referenced_labels - existing_labels
    if not missing:
        return generated_latex
    source_ranges = _section_range_map(template_latex)
    merged = generated_latex
    for section_name, source_range in source_ranges.items():
        source_block = template_latex[source_range[0] : source_range[1]]
        source_labels = set(LABEL_RE.findall(source_block)) & missing
        if not source_labels:
            continue
        if section_name not in _section_range_map(merged):
            continue
        for label in sorted(source_labels):
            for block in re.findall(r"(\\(?:subsection|subsubsection|paragraph)\*?\{[^}]+\}(?:\n\\label\{[^}]+\})?|\\begin\{[^}]+\}.*?\\end\{[^}]+\}|\\label\{[^}]+\})", source_block, re.DOTALL):
                if f"\\label{{{label}}}" in block and f"\\label{{{label}}}" not in merged:
                    insertion_section = _preferred_section_name(merged, label=label) or section_name
                    merged = _insert_block_into_section(
                        merged,
                        section_name=insertion_section,
                        block=block,
                        label=label,
                    )
                    break
        missing -= source_labels
        if not missing:
            break
    merged = _restore_common_generated_section_labels(merged, missing)
    return merged

def _restore_common_generated_section_labels(generated_latex: str, missing_labels: set[str]) -> str:
    """Add safe labels for common generated sections when the source had none.

    Some human source packets reference labels such as ``sec:impl`` from tables
    or figure captions, while some generated templates only supply plain
    section headings.  If a generated manuscript preserves the reference but no
    source block contains the label, insert the label immediately after the
    matching generated section title.  This does not create new content; it only
    restores LaTeX referential integrity for conventional section labels.
    """

    merged = generated_latex
    for label in sorted(missing_labels):
        target_titles = COMMON_GENERATED_SECTION_LABELS.get(label)
        if not target_titles or f"\\label{{{label}}}" in merged:
            continue
        ranges = _section_range_map(merged)
        target_name = next((title for title in target_titles if title in ranges), None)
        if target_name is None:
            continue
        start, end = ranges[target_name]
        section_title_end = merged.find("}", start, end)
        if section_title_end == -1:
            continue
        insert_at = section_title_end + 1
        insertion = f"\n\\label{{{label}}}"
        merged = merged[:insert_at] + insertion + merged[insert_at:]
    merged = _restore_missing_subsection_reference_labels(merged, missing_labels)
    return merged

def _restore_missing_subsection_reference_labels(generated_latex: str, missing_labels: set[str]) -> str:
    """Restore missing subsection labels at the nearest generated subsection.

    Source packets can legitimately mention subsection labels from the author's
    technical material even when generated templates only contain section
    headings.  If the generated text preserves a ``\ref{subsec:...}`` but no
    source block can be reinserted, attach that label to the nearest preceding
    generated subsection in the same manuscript.  This is compile hygiene only:
    it creates an anchor for an already-visible reference without adding prose.
    """

    merged = generated_latex
    for label in sorted(missing_labels):
        if not label.startswith("subsec:") or f"\\label{{{label}}}" in merged:
            continue
        ref_match = re.search(rf"\\(?:eqref|ref)\{{{re.escape(label)}\}}", merged)
        if not ref_match:
            continue
        prefix = merged[: ref_match.start()]
        subsection_matches = list(SUBSECTION_COMMAND_RE.finditer(prefix))
        if subsection_matches:
            target_match = subsection_matches[-1]
        else:
            section_matches = list(SECTION_COMMAND_RE.finditer(prefix))
            if not section_matches:
                continue
            target_match = section_matches[-1]
        insert_at = target_match.end()
        merged = merged[:insert_at] + f"\n\\label{{{label}}}" + merged[insert_at:]
    return merged
