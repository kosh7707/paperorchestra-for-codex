from __future__ import annotations

import re
from typing import Any

from .boundary import is_material_packet_section_title, normalized_claim_projection
from .validator import extract_citation_keys

SECTION_COMMAND_RE = re.compile(r"\\section\{([^}]+)\}")
SUBSECTION_COMMAND_RE = re.compile(r"\\subsection\{([^}]+)\}")
LABEL_RE = re.compile(r"\\label\{([^}]+)\}")
LATEX_CITATION_COMMAND_RE = re.compile(
    r"\\(?P<name>(?!nocite\b)[A-Za-z]*cite[A-Za-z]*)(?P<star>\*)?(?P<opts>(?:\s*\[[^\]]*\]){0,2})\s*\{(?P<keys>[^}]+)\}",
    re.IGNORECASE,
)


def _section_range_map(latex: str) -> dict[str, tuple[int, int]]:
    matches = list(SECTION_COMMAND_RE.finditer(latex))
    ranges: dict[str, tuple[int, int]] = {}
    for idx, match in enumerate(matches):
        start = match.start()
        next_start = matches[idx + 1].start() if idx + 1 < len(matches) else latex.find("\\end{document}", match.end())
        end = next_start if next_start != -1 else len(latex)
        ranges[match.group(1).strip().lower()] = (start, end)
    return ranges


def _canonical_generated_section_title(title: str) -> str:
    raw = title.strip()
    if re.fullmatch(r"\\begin\{abstract\}.*?\\end\{abstract\}", raw, flags=re.DOTALL | re.IGNORECASE):
        raw = "abstract"
    elif re.fullmatch(r"\\+appendix\b.*", raw, flags=re.DOTALL | re.IGNORECASE):
        raw = "appendix"
    section_match = re.fullmatch(r"\\(?:sub)*section\*?\{(.+)\}", raw, flags=re.DOTALL)
    if section_match:
        raw = section_match.group(1).strip()
    normalized = re.sub(r"\s+", " ", raw.lower())
    aliases = {
        "proposed method": "method",
        "methodology": "method",
        "implementation and results": "experiments",
        "implementation results": "experiments",
        "experiments": "experiments",
        "discussion and limitations": "discussion",
    }
    return aliases.get(normalized, normalized)


def _normalized_section_range_map(latex: str) -> dict[str, tuple[int, int]]:
    return {_canonical_generated_section_title(title): span for title, span in _section_range_map(latex).items()}


def _move_macro_definitions_to_preamble(latex: str, macro_block: str) -> str:
    macro_lines = [
        line
        for line in macro_block.splitlines()
        if re.match(r"\s*\\(?:re)?newcommand\b", line)
    ]
    if not macro_lines:
        return latex
    existing_preamble = latex[: max(latex.find("\\begin{document}"), 0)]
    missing = [line for line in macro_lines if line not in existing_preamble]
    if not missing:
        return latex
    begin_index = latex.find("\\begin{document}")
    if begin_index == -1:
        return "\n".join(missing) + "\n" + latex
    return latex[:begin_index] + "\n" + "\n".join(missing) + "\n" + latex[begin_index:]


def _ensure_text_safe_math_macros(latex: str) -> str:
    r"""Make simple math-only macros safe when used in prose.

    User-provided templates often define shorthand macros whose replacement
    bodies are math commands and then use those macros in prose.  That is
    ordinary manuscript-author shorthand, but it can make the generated draft
    fail a strict LaTeX compile.  Normalize only the narrow, safe case: macros
    whose replacement body is a single ``\math*{...}`` command.
    """

    def _replace_math_command_body(match: re.Match[str]) -> str:
        command = match.group(1)
        body = match.group(2)
        if body.startswith("\\ensuremath{"):
            return match.group(0)
        return f"\\newcommand{{\\{command}}}{{\\ensuremath{{{body}}}}}"

    latex = re.sub(
        r"\\newcommand\{\\([A-Za-z]+)\}\{(\\math(?:sf|rm|it|bf|cal|bb|frak|scr)\{[^{}]*\})\}",
        _replace_math_command_body,
        latex,
    )

    def _replace_simple_math_body(match: re.Match[str]) -> str:
        command = match.group(1)
        body = match.group(2)
        if body.startswith("\\ensuremath{"):
            return match.group(0)
        if not any(token in body for token in ("_", "^", "\\")):
            return match.group(0)
        return f"\\newcommand{{\\{command}}}{{\\ensuremath{{{body}}}}}"

    return re.sub(
        r"\\newcommand\{\\([A-Za-z]+)\}\{([^{}\n]+)\}",
        _replace_simple_math_body,
        latex,
    )


INLINE_MATH_RE = re.compile(r"(?<!\$)\$((?:\\.|[^$\n]){1,500})\$(?!\$)")


def _unescaped_brace_delta(text: str) -> int:
    delta = 0
    backslashes = 0
    for char in text:
        if char == "\\":
            backslashes += 1
            continue
        escaped = backslashes % 2 == 1
        backslashes = 0
        if escaped:
            continue
        if char == "{":
            delta += 1
        elif char == "}":
            delta -= 1
    return delta


def _trim_one_trailing_unescaped_brace(text: str) -> str | None:
    stripped = text.rstrip()
    if not stripped.endswith("}"):
        return None
    brace_index = len(stripped) - 1
    backslashes = 0
    probe = brace_index - 1
    while probe >= 0 and stripped[probe] == "\\":
        backslashes += 1
        probe -= 1
    if backslashes % 2 == 1:
        return None
    return stripped[:brace_index] + text[len(stripped) :]


def _repair_inline_math_surplus_closing_brace(latex: str) -> str:
    r"""Repair a narrow LLM LaTeX typo: one extra ``}`` before inline math end.

    The live smoke exposed a generated phrase such as
    ``$\mathbf{Adv}^{...}_{E}(\mathcal{D})}$``.  The intended math is
    otherwise balanced; the final closing brace is surplus.  Only repair inline
    math spans whose unescaped-brace balance is exactly one extra closing brace
    and whose removal would make the span balanced.
    """

    def _replace(match: re.Match[str]) -> str:
        body = match.group(1)
        if _unescaped_brace_delta(body) != -1:
            return match.group(0)
        trimmed = _trim_one_trailing_unescaped_brace(body)
        if trimmed is None or _unescaped_brace_delta(trimmed) != 0:
            return match.group(0)
        return f"${trimmed}$"

    return INLINE_MATH_RE.sub(_replace, latex)


def _remove_material_packet_sections(latex: str) -> str:
    """Drop source-packet control sections from a generated manuscript.

    Smoke-test material packets may include author/operator notes as source
    constraints. They should shape the draft, not appear as final manuscript
    sections. Macro definitions are preserved by moving them into the preamble.
    """
    ranges = _section_range_map(latex)
    rendered = latex
    for title, (start, end) in sorted(ranges.items(), key=lambda item: item[1][0], reverse=True):
        if not is_material_packet_section_title(title):
            continue
        block = rendered[start:end]
        rendered = rendered[:start].rstrip() + "\n\n" + rendered[end:].lstrip()
        if title == "00 core macros":
            rendered = _move_macro_definitions_to_preamble(rendered, block)
    return _ensure_text_safe_math_macros(rendered)


def _ensure_discussion_section_for_claim_boundaries(latex: str, claim_map: dict[str, Any] | None) -> str:
    claims = [
        claim
        for claim in (claim_map or {}).get("claims", [])
        if isinstance(claim, dict)
        and _canonical_generated_section_title(str(claim.get("target_section") or "")) == "discussion"
        and claim.get("required", True)
    ]
    if not claims:
        return latex
    preferred_title = next(
        (
            str(claim.get("target_section") or "").strip()
            for claim in claims
            if str(claim.get("target_section") or "").strip()
        ),
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
    ranges = _normalized_section_range_map(latex)
    if "discussion" in ranges:
        start, end = ranges["discussion"]
        discussion_block = latex[start:end]
        if all(note in discussion_block for note in boundary_notes):
            return latex
        section_title_end = latex.find("}", start, end)
        insert_at = _paragraph_insertion_index(latex, section_title_end + 1 if section_title_end != -1 else start, end)
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

def _rewrite_legacy_scope_notes(latex: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        claim = match.group(1).strip()
        if not claim:
            return match.group(0)
        if not claim.endswith("."):
            claim += "."
        return (
            f"{claim} The statement is scoped to the evidence and assumptions presented in this paper."
        )

    return re.sub(
        r"Source-grounded scope note:\s*(.*?)\s*This sentence is derived from the supplied material and preserves the section's source boundary without adding a new external claim\.",
        _replace,
        latex,
        flags=re.DOTALL,
    )


_MANUSCRIPT_CONTROL_PROSE_REWRITES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?m)^[ \t]*%[ \t]*PaperOrchestra writes this\.[ \t]*\n?"), ""),
    (re.compile(r"\bfollowing\s+the\s+packet\b", re.IGNORECASE), "Based on the stated evidence"),
    (re.compile(r"\b(?:as\s+)?specified\s+in\s+the\s+packet\b", re.IGNORECASE), "According to the stated evidence"),
    (re.compile(r"\b(?:(?:supplied|provided)\s+)?benchmark\s+packet\b", re.IGNORECASE), "benchmark evidence"),
    (re.compile(r"\b(?:(?:supplied|provided)\s+)?empirical\s+packet\b", re.IGNORECASE), "empirical evidence"),
    (re.compile(r"\b(?:(?:supplied|provided)\s+)?review\s+packet\b", re.IGNORECASE), "reviewed evidence"),
    (
        re.compile(
            r"\b(?:supplied|provided)\s+packet\b|\b(?:(?:supplied|provided)\s+)?(?:method|construction|proof|benchmark|empirical|review|source|material)\s+packet\b",
            re.IGNORECASE,
        ),
        "stated evidence",
    ),
    (
        re.compile(
            r"\b(?:supplied|provided)\s+(?:proof|benchmark|empirical|measurement|review)\s+(?:source|logs?)\b",
            re.IGNORECASE,
        ),
        "stated evidence",
    ),
    (re.compile(r"\bsource[-\s]+grounded\b", re.IGNORECASE), "evidence-bounded"),
    (re.compile(r"\bsupplied\s+source\s+(?:boundary|material)\b", re.IGNORECASE), "stated evidence"),
    (re.compile(r"\bprovided\s+source\s+(?:boundary|material)\b", re.IGNORECASE), "stated evidence"),
    (re.compile(r"\bsupplied\s+source\b", re.IGNORECASE), "stated specification"),
    (re.compile(r"\bprovided\s+source\b", re.IGNORECASE), "stated specification"),
    (re.compile(r"\bsupplied\s+technical\s+materials?\b", re.IGNORECASE), "stated evidence"),
    (re.compile(r"\bprovided\s+technical\s+materials?\b", re.IGNORECASE), "stated evidence"),
    (re.compile(r"\bsupplied\s+technical\s+evidence\b", re.IGNORECASE), "stated technical evidence"),
    (re.compile(r"\bprovided\s+technical\s+evidence\b", re.IGNORECASE), "stated technical evidence"),
    (re.compile(r"\b(?:supplied|provided)\s+evidence\b", re.IGNORECASE), "stated evidence"),
    (re.compile(r"\b(?:supplied|provided)\s+theorem\s+statements?\b", re.IGNORECASE), "theorem statements"),
    (re.compile(r"\b(?:supplied|provided|available)\s+logs?\b", re.IGNORECASE), "measurement log"),
    (re.compile(r"\bavailable\s+(?:materials?|sources?|files?)\b", re.IGNORECASE), "stated evidence"),
    (
        re.compile(r"\b(?:supplied|provided)\s+(?:files?|analyses|analysis)\b", re.IGNORECASE),
        "stated evidence",
    ),
    (re.compile(r"\bsupplied\s+materials?\b", re.IGNORECASE), "stated evidence"),
    (re.compile(r"\bprovided\s+materials?\b", re.IGNORECASE), "stated evidence"),
    (re.compile(r"\bsource\s+boundary\b", re.IGNORECASE), "scope boundary"),
    (re.compile(r"\bsource\s+material\b", re.IGNORECASE), "stated evidence"),
    (re.compile(r"\bthe\s+draft\s+must\s+preserve\b", re.IGNORECASE), "the analysis preserves"),
    (re.compile(r"\bbenchmark\s+narrative\s+must\s+report\b", re.IGNORECASE), "the benchmark analysis reports"),
    (re.compile(r"\bdraft\s+remains\s+bounded\b", re.IGNORECASE), "claims remain bounded"),
    (re.compile(r"\bdoes\s+not\s+add\s+an\s+external\s+claim\b", re.IGNORECASE), "does not broaden the paper's claims"),
    (re.compile(r"\bmanuscript\s+plan\b", re.IGNORECASE), "paper outline"),
    (re.compile(r"\bbenchmark\s+packet\b", re.IGNORECASE), "benchmark evidence"),
    (re.compile(r"\bempirical\s+packet\b", re.IGNORECASE), "empirical evidence"),
    (re.compile(r"\breview\s+packet\b", re.IGNORECASE), "reviewed evidence"),
    (re.compile(r"\bquality\s+gate\b", re.IGNORECASE), "quality criterion"),
    (re.compile(r"\bfigures\s+directory\s+is\s+empty\s+in\s+this\s+packet\b", re.IGNORECASE), "figures are not part of this evaluation"),
    (re.compile(r"\b(?:already\s+)?supplied\s+with\s+the\s+stated\s+evidence\b", re.IGNORECASE), "stated in the evidence"),
)


def _sanitize_manuscript_control_prose(latex: str) -> str:
    """Rewrite leaked workflow/control phrases into ordinary manuscript prose.

    The validator must still reject hard prompt/meta leakage. This sanitizer is
    intentionally narrow: it handles common boundary-control phrases that are
    semantically meaningful but should never appear as authoring-process prose
    in a reviewable manuscript.
    """

    rendered = _rewrite_legacy_scope_notes(latex)
    rendered = re.sub(r"\\[Cc]ref\b", r"\\ref", rendered)
    rendered = re.sub(r"\\(Table|Figure|Section|Theorem|Lemma|Corollary|Appendix)(?=\s*~?\s*\\ref\b)", r"\1", rendered)
    rendered = _normalize_portable_citation_commands(rendered)
    for pattern, replacement in _MANUSCRIPT_CONTROL_PROSE_REWRITES:
        rendered = pattern.sub(replacement, rendered)
    return rendered


def _normalize_portable_citation_commands(latex: str) -> str:
    r"""Rewrite natbib/biblatex citation commands to portable LaTeX ``\cite``.

    Fresh smoke templates intentionally keep dependencies minimal.  LLMs often
    produce scholarly citation forms such as ``\citet`` or ``\textcite`` even
    when the template has not loaded natbib/biblatex.  Preserve the cited keys
    but normalize unsupported command forms before the strict compile gate.
    """

    def _replace(match: re.Match[str]) -> str:
        name = match.group("name")
        star = match.group("star") or ""
        opts = match.group("opts") or ""
        keys = match.group("keys")
        if name == "cite" and not star and opts.count("[") <= 1:
            return match.group(0)
        return f"\\cite{{{keys}}}"

    return LATEX_CITATION_COMMAND_RE.sub(_replace, latex)


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
        target = _canonical_generated_section_title(str(claim.get("target_section") or ""))
        ranges = _normalized_section_range_map(rendered)
        if target not in ranges:
            continue
        start, end = ranges[target]
        section_block = rendered[start:end]
        if note.strip() in section_block:
            continue
        section_title_end = rendered.find("}", start, end)
        insert_at = _paragraph_insertion_index(rendered, section_title_end + 1 if section_title_end != -1 else start, end)
        rendered = rendered[:insert_at] + "\n" + note + rendered[insert_at:]
    return _repair_inline_math_surplus_closing_brace(rendered)


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


def _restore_common_generated_section_labels(generated_latex: str, missing_labels: set[str]) -> str:
    """Add safe labels for common generated sections when the source had none.

    Some human source packets reference labels such as ``sec:impl`` from tables
    or figure captions, while the fresh-smoke template only supplies plain
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
    technical material even when the fresh smoke template only contains section
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


def _citation_map_for_selected_sections(source_latex: str, citation_map: dict[str, Any], selected_sections: list[str]) -> dict[str, Any]:
    if not citation_map:
        return {}
    ranges = _section_range_map(source_latex)
    selected_keys: set[str] = set()
    for section_name in selected_sections:
        section_range = ranges.get(section_name.strip().lower())
        if section_range is None:
            continue
        block = source_latex[section_range[0] : section_range[1]]
        selected_keys.update(extract_citation_keys(block))
    if not selected_keys:
        return citation_map
    subset = {key: value for key, value in citation_map.items() if key in selected_keys}
    return subset or citation_map
