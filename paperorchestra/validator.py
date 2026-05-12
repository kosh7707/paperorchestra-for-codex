from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .boundary import control_prose_markers, normalized_coverage_groups

COMPARATIVE_CLAIM_PATTERNS = [
    "state-of-the-art",
    "sota",
    "outperform",
    "outperforms",
    "outperformed",
    "beats",
    "better than",
    "superior to",
]
PROMPT_META_LEAKAGE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bcaption\s*intent\b",
        r"\brendering[_\s-]*brief\b",
        r"\bsource[_\s-]*fidelity(?:[_\s-]*notes)?\b",
        r"\binternal\s+visual\s+prompt\b",
        r"\bgeneration\s+objective\b|\binternal\s+generation\s+objective\b",
        r"\bfigure\s+prompt\b",
        r"\bprompt\s*/\s*meta\b|\bprompt\s+meta\b",
        r"\bsupplied\s+source\s+(?:boundary|material)\b",
        r"\bprovided\s+(?:method\s+)?material\b",
        r"\bsource[-\s]+grounded\b",
        r"\bsource\s+boundary\b",
        r"\bthe\s+draft\s+must\s+preserve\b",
        r"\bbenchmark\s+narrative\s+must\s+report\b",
        r"\bdraft\s+remains\s+bounded\b",
        r"\bdoes\s+not\s+add\s+an\s+external\s+claim\b",
        r"\bskipped_due_to_upstream_fail\b",
        r"\bdata_block\b|<\s*/?\s*DATA_BLOCK\b",
        r"\breviewer_feedback\b",
        r"\bscore_redaction\b|\bwriter_blind_to_reviewer_scores\b",
        r"\bas an ai\b",
        r"\blorem\s+ipsum\b|\bplaceholder\s+(?:figure|image|asset|text|caption)\b",
        r"\bTODO\b|\bTBD\b|\\todo\b",
        r"\bproof\s+omitted\b|\bomitted\s+proof\b",
        r"\binsert\s+(?:the\s+)?figure\b|\bfigure\s+to\s+be\s+inserted\b",
        r"\bcitation_map\.json\b|\bsection_writing\b",
        r"\bnarrative_plan(?:\.json)?\b|\bclaim_map(?:\.json)?\b|\bcitation_placement_plan(?:\.json)?\b",
        r"\bauthor[_\s-]*facing[_\s-]*writer[_\s-]*brief\b|\bwriter[_\s-]*brief(?:\.json)?\b",
        r"\bclaim_id\b|\bclaim-\d{3,}\b",
        r"\bartifact[-\s]+governed\s+drafting\b",
        r"\bpromotion[-\s]+time\s+validation\b",
        r"\b(?:supplied|provided)\s+packet\b|\b(?:supplied|provided)\s+(?:proof|benchmark|empirical|review|source|material)\s+packet\b",
        r"\brevised\s+manuscript\b|\bsupplied\s+(?:library|material|technical\s+evidence)\b|\b(?:supplied|provided)\s+(?:proof|benchmark|empirical|measurement|review)\s+(?:source|logs?)\b|\bbenchmark\s+packet\b|\bempirical\s+packet\b|\bfigures\s+directory\s+is\s+empty\s+in\s+this\s+packet\b|\bquality\s+gate\b|\breview\s+packet\b",
        # Catch leaked source-packet headings such as
        # ``\section{Claim Boundaries for the Draft}`` without banning ordinary
        # scholarly phrases like "assumptions, composition rationale, and claim
        # boundaries" in a limitations discussion.
        r"\\(?:sub)*section\*?\{\s*claim\s+boundaries(?:\s+for\s+(?:the\s+)?.+?\s+draft)?\s*\}",
        r"\bauthor\s+notes(?:\s+for\s+.+)?\b",
    ]
]

SECTION_RE = re.compile(r"\\section\*?\{([^}]+)\}")
FIGURE_ENV_RE = re.compile(r"\\begin\{(figure\*?)\}(?:\[([^\]]*)\])?(.*?)\\end\{\1\}", re.DOTALL)
CAPTION_RE = re.compile(r"\\caption\{([^}]*)\}")
REF_RE = re.compile(r"\\ref\{([^}]+)\}")
LABEL_RE = re.compile(r"\\label\{([^}]+)\}")
CITE_COMMAND_RE = re.compile(
    r"(\\(?!nocite\b)(?:[A-Za-z]*cite[A-Za-z]*)\*?(?:\[[^\]]*\]){0,2})\{([^}]+)\}",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    severity: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class FigurePlacementWarning:
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def extract_citation_keys(latex: str) -> set[str]:
    keys: set[str] = set()
    for match in CITE_COMMAND_RE.finditer(latex):
        for key in match.group(2).split(","):
            stripped = key.strip()
            if stripped:
                keys.add(stripped)
    return keys


def _citation_key_tokens(key: str) -> list[str]:
    return re.findall(r"[A-Z][a-z]*|[A-Z]+(?![a-z])|\d+|[a-z]+", key)


def _citation_key_aliases(key: str) -> set[str]:
    aliases = {key}
    tokens = _citation_key_tokens(key)
    if not tokens:
        return aliases
    digit_idx = next((idx for idx, token in enumerate(tokens) if token.isdigit()), len(tokens))
    prefix = tokens[:digit_idx]
    suffix = "".join(tokens[digit_idx:])
    acronym = "".join(token[0].upper() for token in prefix if token and not token.isdigit())
    if acronym:
        aliases.add(acronym + suffix)
    return aliases


def canonicalize_citation_keys(latex: str, citation_map: dict[str, Any]) -> tuple[str, dict[str, str]]:
    alias_map: dict[str, str | None] = {}
    for key in citation_map:
        for alias in _citation_key_aliases(key):
            lowered = alias.lower()
            if lowered not in alias_map:
                alias_map[lowered] = key
            elif alias_map[lowered] != key:
                alias_map[lowered] = None

    replacements: dict[str, str] = {}

    def _replace(match: re.Match[str]) -> str:
        raw_keys = [part.strip() for part in match.group(2).split(",")]
        updated: list[str] = []
        changed = False
        for raw_key in raw_keys:
            if not raw_key:
                continue
            if raw_key in citation_map:
                updated.append(raw_key)
                continue
            canonical = alias_map.get(raw_key.lower())
            if canonical and canonical not in {None, ""}:
                replacements[raw_key] = canonical
                updated.append(canonical)
                changed = True
            else:
                updated.append(raw_key)
        if not changed:
            return match.group(0)
        return match.group(1) + "{" + ", ".join(updated) + "}"

    return CITE_COMMAND_RE.sub(_replace, latex), replacements


def extract_decimal_like_tokens(text: str) -> set[str]:
    tokens = set()
    for match in re.finditer(r"\b\d+\.\d+(?:%|x|×)?\b|\b\d+\.\d+\\times\b|\b\d+%", text):
        token = match.group(0)
        token = token.removesuffix(r"\times").removesuffix("×").removesuffix("x")
        tokens.add(token)
    return tokens


def _sanitize_layout_numbers(latex: str) -> str:
    sanitized = re.sub(r"\\begin\{thebibliography\}.*?\\end\{thebibliography\}", "<bibliography>", latex, flags=re.S)
    sanitized = re.sub(r"width\s*=\s*\d+\.\d+\\[A-Za-z]+", "width=<layout>", sanitized)
    sanitized = re.sub(r"scale\s*=\s*\d+\.\d+", "scale=<layout>", sanitized)
    sanitized = re.sub(r"p\{\d+\.\d+\\[A-Za-z]+\}", "p{<layout>}", sanitized)
    sanitized = re.sub(r"\\begin\{minipage\}\{\d+\.\d+\\[A-Za-z]+\}", r"\\begin{minipage}{<layout>}", sanitized)
    sanitized = re.sub(r"\\renewcommand\{\\arraystretch\}\{\d+\.\d+\}", r"\\renewcommand{\\arraystretch}{<layout>}", sanitized)
    sanitized = re.sub(r"\\setlength\{[^}]+\}\{\d+\.\d+\\[A-Za-z]+\}", r"\\setlength{<layout>}{<layout>}", sanitized)
    return sanitized


def check_unknown_citations(latex: str, citation_map: dict[str, Any]) -> list[ValidationIssue]:
    cited_keys = extract_citation_keys(latex)
    unknown_keys = sorted(key for key in cited_keys if key not in citation_map)
    if not unknown_keys:
        return []
    return [
        ValidationIssue(
            code="unknown_citation_keys",
            severity="error",
            message=f"Unknown citation keys referenced in LaTeX: {', '.join(unknown_keys)}",
        )
    ]


def check_citation_coverage(latex: str, citation_map: dict[str, Any]) -> list[ValidationIssue]:
    if not citation_map:
        return []
    cited_keys = extract_citation_keys(latex)
    population = len(citation_map)
    if population <= 10:
        required_citation_count = population
    elif population <= 25:
        required_citation_count = max(1, int(round(population * 0.85)))
    elif population <= 50:
        required_citation_count = max(1, int(round(population * 0.8)))
    else:
        required_citation_count = max(1, int(round(population * 0.7)))
    if len(cited_keys) >= required_citation_count:
        return []
    return [
        ValidationIssue(
            code="citation_coverage_insufficient",
            severity="error",
            message=(
                f"Insufficient citation coverage: cited {len(cited_keys)} verified papers, "
                f"need at least {required_citation_count}."
            ),
        )
    ]


def check_figure_file_coverage(latex: str, figures_dir: str | None) -> list[ValidationIssue]:
    if not figures_dir:
        return []
    figure_dir_path = Path(figures_dir)
    required_figure_names = [
        path.name
        for path in figure_dir_path.iterdir()
        if path.is_file() and not path.name.startswith(".")
    ]
    missing_figures = [name for name in required_figure_names if name not in latex]
    if not missing_figures:
        return []
    return [
        ValidationIssue(
            code="figure_file_not_referenced",
            severity="warning",
            message=f"Provided figures not referenced in LaTeX: {', '.join(missing_figures)}",
        )
    ]


def check_plot_plan_coverage(latex: str, plot_manifest: dict[str, Any] | None) -> list[ValidationIssue]:
    if not plot_manifest:
        return []
    lowered_latex = latex.lower()
    missing_plot_coverage = []
    for figure in plot_manifest.get("figures", []):
        figure_id = figure.get("figure_id", "")
        title = figure.get("title", "")
        caption = figure.get("caption", "")
        if figure_id and figure_id.lower() in lowered_latex:
            continue
        if title and title.lower() in lowered_latex:
            continue
        if caption and caption.lower() in lowered_latex:
            continue
        if figure_id:
            missing_plot_coverage.append(figure_id)
    if not missing_plot_coverage:
        return []
    return [
        ValidationIssue(
            code="plot_plan_not_reflected",
            severity="error",
            message="Plot-plan figures are not represented in the manuscript: " + ", ".join(sorted(missing_plot_coverage)),
        )
    ]


def check_generated_plot_asset_usage(latex: str, plot_assets_index: dict[str, Any] | None) -> list[ValidationIssue]:
    if not plot_assets_index:
        return []
    assets = plot_assets_index.get("assets", []) if isinstance(plot_assets_index, dict) else []
    missing_assets = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        if asset.get("asset_kind") == "generated_placeholder" or asset.get("review_status") == "human_final_artwork_required":
            continue
        filename = asset.get("filename")
        snippet_path = asset.get("latex_snippet_path")
        latex_path = asset.get("latex_path")
        if isinstance(snippet_path, str) and snippet_path and snippet_path in latex:
            continue
        if isinstance(latex_path, str) and latex_path and latex_path in latex:
            continue
        if isinstance(filename, str) and filename and filename in latex:
            continue
        if isinstance(filename, str) and filename:
            missing_assets.append(filename)
    if not missing_assets:
        return []
    return [
        ValidationIssue(
            code="generated_plot_asset_not_used",
            severity="warning",
            message="Generated plot assets are not referenced in the manuscript: " + ", ".join(sorted(missing_assets)),
        )
    ]


def _normalize_section_title(title: str) -> str:
    raw = title.strip()
    if re.fullmatch(r"\\+appendix\b.*", raw, flags=re.DOTALL | re.IGNORECASE):
        raw = "appendix"
    if re.fullmatch(r"\\+begin\{abstract\}", raw, flags=re.DOTALL | re.IGNORECASE):
        raw = "abstract"
    section_match = re.fullmatch(r"\\(?:sub)*section\*?\{(.+)\}", raw, flags=re.DOTALL)
    if section_match:
        raw = section_match.group(1).strip()
    normalized = re.sub(r"\s+", " ", raw.lower())
    aliases = {
        "proposed method": "method",
        "methodology": "method",
        "implementation and results": "experiments",
        "implementation results": "experiments",
        "discussion and limitations": "discussion",
    }
    return aliases.get(normalized, normalized)


def _section_bodies(latex: str) -> dict[str, str]:
    matches = list(SECTION_RE.finditer(latex))
    result: dict[str, str] = {}
    for idx, match in enumerate(matches):
        title = _normalize_section_title(match.group(1))
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else latex.find(r"\end{document}", start)
        if end == -1:
            end = len(latex)
        result[title] = latex[start:end]
    return result


def _substantive_text(text: str) -> str:
    stripped = re.sub(r"\\begin\{thebibliography\}.*", "", text, flags=re.DOTALL)
    stripped = re.sub(r"\\begin\{[^}]+\}|\\end\{[^}]+\}", " ", stripped)
    stripped = re.sub(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})?", " ", stripped)
    stripped = re.sub(r"[%].*", " ", stripped)
    stripped = re.sub(r"[^A-Za-z0-9가-힣]+", " ", stripped)
    return re.sub(r"\s+", " ", stripped).strip()


def _line_number(text: str, index: int) -> int:
    return text.count("\n", 0, max(0, index)) + 1


def _section_records(latex: str) -> list[dict[str, Any]]:
    matches = list(SECTION_RE.finditer(latex))
    records: list[dict[str, Any]] = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else latex.find(r"\end{document}", match.end())
        if end == -1:
            end = len(latex)
        title = match.group(1).strip()
        records.append(
            {
                "title": title,
                "normalized_title": _normalize_section_title(title),
                "start": start,
                "end": end,
                "line": _line_number(latex, start),
            }
        )
    return records


def _section_for_index(latex: str, index: int) -> dict[str, Any] | None:
    for section in _section_records(latex):
        if section["start"] <= index < section["end"]:
            return section
    return None


def _source_figure_labels(source_latex: str | None) -> set[str]:
    if not source_latex:
        return set()
    labels: set[str] = set()
    for match in FIGURE_ENV_RE.finditer(source_latex):
        label_match = LABEL_RE.search(match.group(3))
        if label_match:
            labels.add(label_match.group(1))
    return labels


def _figure_source_origin(block: str, label: str | None, source_labels: set[str], *, prefix: str = "") -> str:
    if "PaperOrchestra:auto-repaired" in block or "PaperOrchestra:auto-repaired" in prefix:
        return "auto_repaired"
    if label and label in source_labels:
        return "source_preserved"
    return "model_written"


def _figure_warning(
    code: str,
    *,
    label: str | None,
    detail: str,
) -> FigurePlacementWarning:
    subject = label or "<unlabeled>"
    return FigurePlacementWarning(code=code, message=f"{subject}: {detail}")


def build_figure_placement_review(
    latex: str,
    *,
    source_latex: str | None = None,
    manuscript_path: str | None = None,
    pdf_path: str | None = None,
    tail_ratio_threshold: float = 0.85,
    far_reference_line_threshold: int = 80,
) -> dict[str, Any]:
    total_lines = max(1, latex.count("\n") + 1)
    sections = _section_records(latex)
    source_labels = _source_figure_labels(source_latex)
    conclusion_start = next((section["start"] for section in sections if section["normalized_title"] == "conclusion"), None)
    bibliography_start = latex.find(r"\bibliographystyle")
    if bibliography_start == -1:
        bibliography_start = latex.find(r"\bibliography")
    figures: list[dict[str, Any]] = []
    warnings: list[FigurePlacementWarning] = []
    tail_figures: list[int] = []

    for idx, match in enumerate(FIGURE_ENV_RE.finditer(latex), start=1):
        env = match.group(1)
        placement = match.group(2) or ""
        block = match.group(0)
        body = match.group(3)
        label_match = LABEL_RE.search(body)
        label = label_match.group(1) if label_match else None
        caption_match = CAPTION_RE.search(body)
        caption = caption_match.group(1).strip() if caption_match else ""
        start = match.start()
        end = match.end()
        start_line = _line_number(latex, start)
        end_line = _line_number(latex, end)
        section = _section_for_index(latex, start)
        section_title = section["title"] if section else ""
        refs = []
        if label:
            refs = [m for m in REF_RE.finditer(latex) if m.group(1) == label and not (start <= m.start() < end)]
        first_ref = refs[0] if refs else None
        first_ref_line = _line_number(latex, first_ref.start()) if first_ref else None
        first_ref_distance_lines = start_line - first_ref_line if first_ref_line is not None else None
        figure_warnings: list[FigurePlacementWarning] = []

        if conclusion_start is not None and start >= conclusion_start:
            figure_warnings.append(
                _figure_warning("after_conclusion", label=label, detail="Figure appears in or after the Conclusion section.")
            )
        if bibliography_start != -1 and start >= bibliography_start:
            figure_warnings.append(
                _figure_warning("tail_clump", label=label, detail="Figure appears after the bibliography hook area.")
            )
        elif start_line / total_lines >= tail_ratio_threshold:
            tail_figures.append(idx - 1)
        if first_ref_distance_lines is not None and first_ref_distance_lines > far_reference_line_threshold:
            figure_warnings.append(
                _figure_warning(
                    "far_from_first_reference",
                    label=label,
                    detail=f"Figure is {first_ref_distance_lines} lines after its first reference.",
                )
            )
        if not placement.strip():
            figure_warnings.append(
                _figure_warning("placement_hint_missing", label=label, detail="Figure environment has no placement specifier.")
            )
        include_line = next((line for line in body.splitlines() if "\\includegraphics" in line or "\\input{" in line), "")
        if env == "figure*" and ("\\columnwidth" in include_line or "\\linewidth" in include_line):
            figure_warnings.append(
                _figure_warning(
                    "wide_figure_mismatch",
                    label=label,
                    detail="figure* uses a narrow-width include that looks single-column.",
                )
            )
        if env == "figure" and "\\textwidth" in include_line:
            figure_warnings.append(
                _figure_warning(
                    "wide_figure_mismatch",
                    label=label,
                    detail="Single-column figure uses textwidth and may need figure*.",
                )
            )

        warnings.extend(figure_warnings)
        figures.append(
            {
                "label": label or f"unnamed_{idx}",
                "caption": caption,
                "section_title": section_title,
                "figure_line": start_line,
                "figure_end_line": end_line,
                "figure_page": None,
                "first_reference_line": first_ref_line,
                "first_reference_page": None,
                "reference_distance_lines": first_ref_distance_lines,
                "reference_distance_pages": None,
                "placement_environment": env,
                "placement_specifier": placement,
                "source_origin": _figure_source_origin(
                    block,
                    label,
                    source_labels,
                    prefix=latex[max(0, start - 120) : start],
                ),
                "warning_codes": [warning.code for warning in figure_warnings],
            }
        )

    if len(tail_figures) > 1:
        for index in tail_figures:
            warning = _figure_warning(
                "tail_clump",
                label=figures[index]["label"],
                detail="Figure is clustered in the tail of the manuscript.",
            )
            warnings.append(warning)
            figures[index]["warning_codes"].append("tail_clump")

    return {
        "manuscript_path": manuscript_path,
        "pdf_path": pdf_path,
        "generated_at": None,
        "figures": figures,
        "warnings": [warning.to_dict() for warning in warnings],
        "summary": {
            "figure_count": len(figures),
            "warning_count": len(warnings),
            "warning_codes": sorted({warning.code for warning in warnings}),
        },
    }


def check_expected_section_substance(
    latex: str,
    expected_section_titles: list[str] | None,
    *,
    min_body_chars: int = 120,
) -> list[ValidationIssue]:
    if not expected_section_titles:
        return []
    bodies = _section_bodies(latex)
    missing: list[str] = []
    shallow: list[str] = []
    ignored = {"abstract", "appendix", "references", "bibliography"}
    for raw_title in expected_section_titles:
        title = _normalize_section_title(raw_title)
        if not title or title in ignored or title.startswith("appendix"):
            continue
        body = bodies.get(title)
        if body is None:
            missing.append(raw_title)
            continue
        if len(_substantive_text(body)) < min_body_chars:
            shallow.append(raw_title)
    issues = []
    if missing:
        issues.append(
            ValidationIssue(
                code="expected_section_missing",
                severity="error",
                message="Expected sections are missing from the manuscript: " + ", ".join(missing),
            )
        )
    if shallow:
        issues.append(
            ValidationIssue(
                code="expected_section_too_shallow",
                severity="error",
                message=f"Expected sections have too little substantive body text (<{min_body_chars} chars): " + ", ".join(shallow),
            )
        )
    return issues


def check_numeric_grounding(latex: str, experimental_log_text: str | None) -> list[ValidationIssue]:
    if not experimental_log_text:
        return []
    allowed_numeric_tokens = extract_decimal_like_tokens(experimental_log_text)
    manuscript_numeric_tokens = extract_decimal_like_tokens(_sanitize_layout_numbers(latex))
    unsupported_numeric_tokens = sorted(manuscript_numeric_tokens - allowed_numeric_tokens)
    if not unsupported_numeric_tokens:
        return []
    return [
        ValidationIssue(
            code="numeric_grounding_mismatch",
            severity="error",
            message=(
                "Manuscript contains decimal/percent values not grounded in the experimental log: "
                + ", ".join(unsupported_numeric_tokens)
            ),
        )
    ]


def check_comparative_claims(latex: str, experimental_log_text: str | None) -> list[ValidationIssue]:
    if not experimental_log_text:
        return []
    lowered_log = experimental_log_text.lower()
    lowered_latex = latex.lower()
    unsupported_claim_patterns = [
        pattern for pattern in COMPARATIVE_CLAIM_PATTERNS if pattern in lowered_latex and pattern not in lowered_log
    ]
    if not unsupported_claim_patterns:
        return []
    return [
        ValidationIssue(
            code="unsupported_comparative_claim",
            severity="warning",
            message=(
                "Manuscript contains comparative claims not evidenced in the experimental log: "
                + ", ".join(sorted(set(unsupported_claim_patterns)))
            ),
        )
    ]


def check_prompt_meta_leakage(latex: str) -> list[ValidationIssue]:
    visible_text = _visible_latex_text(latex)
    if not any(pattern.search(visible_text) for pattern in PROMPT_META_LEAKAGE_PATTERNS) and not control_prose_markers(visible_text):
        return []
    return [
        ValidationIssue(
            code="prompt_meta_leakage",
            severity="error",
            message="Manuscript contains prompt/meta or internal generation text that must not appear in reviewable drafts.",
        )
    ]


def _visible_latex_text(latex: str) -> str:
    lines = []
    for line in latex.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("%"):
            continue
        lines.append(re.sub(r"(?<!\\)%.*", "", line))
    text = "\n".join(lines)
    text = re.sub(r"\\begin\{thebibliography\}.*?\\end\{thebibliography\}", " ", text, flags=re.DOTALL)
    text = re.sub(r"\\bibliographystyle\{[^}]+\}|\\bibliography\{[^}]+\}", " ", text)
    return text


def _section_visible_text(latex: str, title: str) -> str:
    bodies = _section_bodies(_visible_latex_text(latex))
    return _substantive_text(bodies.get(_normalize_section_title(title), ""))


def _section_visible_latex(latex: str, title: str) -> str:
    bodies = _section_bodies(_visible_latex_text(latex))
    return bodies.get(_normalize_section_title(title), "")


def _claim_guard_text(text: str) -> str:
    stripped = re.sub(r"\\begin\{thebibliography\}.*", "", text, flags=re.DOTALL)
    stripped = re.sub(r"\\begin\{[^}]+\}|\\end\{[^}]+\}", " ", stripped)
    stripped = re.sub(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?", " ", stripped)
    stripped = stripped.replace("{", " ").replace("}", " ")
    stripped = re.sub(r"[%].*", " ", stripped)
    stripped = re.sub(r"[^A-Za-z0-9가-힣.,;:!?\"'“”‘’-]+", " ", stripped)
    return re.sub(r"\s+", " ", stripped).strip()


def _boundary_negates_phrase(prefix: str) -> bool:
    if re.search(
        r"\b(?:should\s+)?not\s+be\s+interpreted\s+as\s+"
        r"(?:(?:showing|meaning|implying)(?:[\w\s,;:-]{0,80})\bthat|evidence\s+that)\s*$",
        prefix,
    ):
        return True
    if re.search(r"\bno\s+one\s+should\s+(?:conclude|infer|read\s+this\s+as\s+claiming)\s+that\s*$", prefix):
        return True
    if re.search(r"\bnot\s+true\s+that\s*$", prefix):
        return True
    if re.search(r"\bno\s+evidence\s+(?:shows|suggests|demonstrates|establishes|implies)\s+that\s*$", prefix):
        return True
    if re.search(
        r"\b(?:the\s+)?(?:goal|aim|objective|purpose)\s+is\s+not\s+to\s+"
        r"(?:claim|assert|show|establish|demonstrate|imply|mean)(?:\s+that)?\s*$",
        prefix,
    ):
        return True
    direct_boundary_verb = r"(?:claim|assert|show|establish|demonstrate|imply|mean)"
    direct_boundary_modifier = r"(?:currently|directly|explicitly|actually|yet)"
    direct_boundary = re.search(
        r"\b(?:does|do)\s+not\s+"
        rf"(?:(?:{direct_boundary_modifier})\s+){{0,3}}"
        rf"{direct_boundary_verb}"
        rf"(?:\s*,\s*{direct_boundary_verb})*"
        rf"(?:\s*,?\s+(?:or|and)\s+{direct_boundary_verb})?"
        r"(?:\s+that)?\s*$",
        prefix,
    )
    if direct_boundary:
        leading = prefix[: direct_boundary.start()]
        current_sentence = re.split(r"[.;!?]", leading)[-1]
        attribution_subject = r"(?:the\s+)?[a-z][a-z-]*(?:\s+[a-z][a-z-]*){0,3}"
        reporting_verb = (
            r"(?:wrote|writes|said|say|says|state|states|stated|claim|claims|claimed|note|notes|noted|"
            r"argue|argues|argued|report|reports|reported|read|reads|comment|comments|remark|remarks)"
        )
        if (
            re.search(r"\b(?:according\s+to|per)\b", current_sentence)
            or re.search(r"\b(?:quoted?|quotation|excerpt)\s*[:,-]", current_sentence)
            or re.search(r"\bquote\b.*[:,-]", current_sentence)
            or re.search(attribution_subject + r"\s+" + reporting_verb + r"\s*[:,-]", current_sentence)
            or re.search(reporting_verb + r"\s*[:,-]\s*$", current_sentence)
        ):
            return False
        leading_segment = re.split(r"(?:[.;:!?]|,|\bbut\b|\byet\b(?!\s*$)|\bhowever\b)", leading)[-1].strip()
        safe_subject = (
            r"(?:"
            r"(?:the|this|our)(?:\s+current)?\s+(?:paper|manuscript|draft|system|workflow|evaluation|evidence|result|results)"
            r"|we"
            r"|it"
            r"|our\s+(?:paper|manuscript|draft|system|workflow|evaluation)"
            r")"
        )
        if re.fullmatch(
            r"(?:(?:overall|broadly|more\s+broadly)\s+)?"
            rf"{safe_subject}"
            r"(?:\s+(?:also|therefore|thus|accordingly))?"
            r"(?:\s+does\s+not\s+[a-z][a-z-]*(?:\s+[a-z][a-z-]*){0,8}\s+and)?",
            leading_segment,
        ):
            return True
    segment = re.split(r"(?:[.;:!?]|,|\bbut\b|\byet\b(?!\s*$)|\bhowever\b)", prefix)[-1]
    direct_negator = r"(?:never|no|without|non-?|not\s+(?:yet\s+|currently\s+|already\s+|actually\s+|really\s+|a\s+|an\s+|the\s+|that\s+)?)"
    return bool(re.search(r"\b" + direct_negator + r"$", segment))


def _contains_unnegated_phrase(text: str, phrase: str) -> bool:
    phrase_text = _substantive_text(phrase).lower()
    if not phrase_text:
        return False
    normalized = " " + _claim_guard_text(text).lower() + " "
    phrase_separator = r"(?:\s+|-)"
    pattern = re.compile(r"(?<!\w)" + phrase_separator.join(re.escape(part) for part in phrase_text.split()) + r"(?!\w)")
    for match in pattern.finditer(normalized):
        prefix = normalized[max(0, match.start() - 160) : match.start()]
        if _boundary_negates_phrase(prefix):
            continue
        return True
    return False


def _coverage_term_variants(term: str) -> tuple[str, ...]:
    normalized = str(term).strip().lower()
    if not normalized:
        return ()
    irregular = {
        "boundary": ("boundary", "boundaries"),
        "boundaries": ("boundary", "boundaries"),
    }
    if normalized in irregular:
        return irregular[normalized]
    variants = {normalized}
    if normalized.endswith("y") and len(normalized) > 1:
        variants.add(normalized[:-1] + "ies")
    elif normalized.endswith("ies") and len(normalized) > 3:
        variants.add(normalized[:-3] + "y")
    elif normalized.endswith("s") and len(normalized) > 3:
        variants.add(normalized[:-1])
    else:
        variants.add(normalized + "s")
    return tuple(sorted(variants))


def _coverage_term_position(section_text: str, term: str) -> int:
    lowered = section_text.lower()
    positions = [lowered.find(variant) for variant in _coverage_term_variants(term)]
    found = [position for position in positions if position >= 0]
    return min(found) if found else -1


def _terms_nearby(section_text: str, terms: list[str], *, window: int = 360) -> bool:
    lowered = section_text.lower()
    positions = []
    for term in terms:
        idx = _coverage_term_position(lowered, str(term))
        if idx < 0:
            return False
        positions.append(idx)
    return max(positions) - min(positions) <= window


def check_claim_map_coverage(latex: str, claim_map: dict[str, Any] | None) -> list[ValidationIssue]:
    if not isinstance(claim_map, dict):
        return []
    issues: list[ValidationIssue] = []
    visible = _visible_latex_text(latex)
    if re.search(r"\bclaim_id\b|\bclaim-\d{3,}\b", visible, re.IGNORECASE):
        issues.append(
            ValidationIssue(
                code="prompt_meta_leakage",
                severity="error",
                message="Manuscript visibly leaks claim-map identifiers or claim_id metadata.",
            )
        )
    for claim in claim_map.get("claims") or []:
        if not isinstance(claim, dict) or not claim.get("required"):
            continue
        claim_id = str(claim.get("id") or "required-claim")
        target = str(claim.get("target_section") or "")
        section_text = _section_visible_text(latex, target)
        if not section_text:
            issues.append(
                ValidationIssue(
                    code="required_claim_wrong_section",
                    severity="error",
                    message=f"Required claim {claim_id} is missing from target section {target}.",
                )
            )
            continue
        if not claim.get("evidence_anchors"):
            issues.append(
                ValidationIssue(
                    code="source_material_claim_omitted",
                    severity="error",
                    message=f"Required claim {claim_id} lacks evidence anchors and cannot be enforced safely.",
                )
            )
            continue
        groups = claim.get("coverage_groups") or []
        if not groups:
            flat_terms = claim.get("coverage_terms") or []
            groups = [[term] for term in flat_terms]
        satisfied = 0
        isolated_hits = 0
        for group in groups:
            terms = [str(term) for term in group if str(term).strip()]
            if not terms:
                continue
            if all(term.lower() in section_text.lower() for term in terms):
                isolated_hits += 1
            if _terms_nearby(section_text, terms):
                satisfied += 1
        needed = max(1, min(len(groups), 2 if len(groups) <= 2 else 2))
        if satisfied < needed:
            code = "required_claim_keyword_stuffing" if isolated_hits >= needed else "required_claim_missing"
            issues.append(
                ValidationIssue(
                    code=code,
                    severity="error",
                    message=f"Required claim {claim_id} is not meaningfully covered in target section {target}.",
                )
            )
    return issues


def check_citation_placement(latex: str, citation_placement_plan: dict[str, Any] | None) -> list[ValidationIssue]:
    if not isinstance(citation_placement_plan, dict):
        return []
    issues: list[ValidationIssue] = []
    for placement in citation_placement_plan.get("placements") or []:
        if not isinstance(placement, dict):
            continue
        claim_id = str(placement.get("claim_id") or "claim")
        target = str(placement.get("target_section") or "")
        section_text = _section_visible_latex(latex, target)
        keys = [str(key) for key in placement.get("citation_keys") or [] if str(key).strip()]
        missing = [key for key in keys if key not in extract_citation_keys(section_text)]
        if missing:
            issues.append(
                ValidationIssue(
                    code="citation_placement_missing",
                    severity="error",
                    message=f"Citation placement for {claim_id} is missing key(s) in {target}: {', '.join(missing)}",
                )
            )
    return issues


def _narrative_terms_from_item(item: Any) -> list[str]:
    if isinstance(item, dict):
        groups = normalized_coverage_groups(item)
        terms = [term for group in groups for term in group]
        if terms:
            return terms[:8]
        text = str(item.get("authorial_claim") or item.get("beat") or item.get("text") or "")
    else:
        text = str(item)
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{3,}", text)[:6]


def _narrative_item_covered(section_text: str, item: Any) -> bool:
    if isinstance(item, dict) and item.get("coverage_groups"):
        for group in normalized_coverage_groups(item):
            terms = [str(term) for term in group if str(term).strip()]
            if terms and _terms_nearby(section_text, terms):
                return True
        return False
    terms = _narrative_terms_from_item(item)
    return not terms or any(term.lower() in section_text.lower() for term in terms)


def check_narrative_section_roles(latex: str, narrative_plan: dict[str, Any] | None) -> list[ValidationIssue]:
    if not isinstance(narrative_plan, dict):
        return []
    issues: list[ValidationIssue] = []
    for role in narrative_plan.get("section_roles") or []:
        if not isinstance(role, dict):
            continue
        title = str(role.get("section_title") or "")
        section_latex = _section_visible_latex(latex, title)
        section_text = _substantive_text(section_latex)
        role_items = role.get("coverage_requirements") or role.get("must_cover") or []
        for item in role_items:
            if not _narrative_item_covered(section_text, item):
                label = str(item.get("authorial_claim") if isinstance(item, dict) else item)[:120]
                issues.append(
                    ValidationIssue(
                        code="narrative_section_role_missing",
                        severity="error",
                        message=f"Section {title} does not cover required narrative role item: {label}",
                    )
                )
        for forbidden in role.get("must_not_claim") or []:
            if _contains_unnegated_phrase(section_latex, str(forbidden)):
                issues.append(
                    ValidationIssue(
                        code="narrative_forbidden_claim_present",
                        severity="error",
                        message=f"Section {title} contains forbidden narrative claim: {forbidden}",
                    )
                )
    for beat in narrative_plan.get("story_beats") or []:
        if not isinstance(beat, dict):
            continue
        target = str(beat.get("target_section") or "")
        section_text = _section_visible_text(latex, target)
        if not _narrative_item_covered(section_text, beat):
            issues.append(
                ValidationIssue(
                    code="narrative_story_beat_missing",
                    severity="error",
                    message=f"Story beat is missing from target section {target}: {str(beat.get('beat'))[:120]}",
                )
            )
    return issues


def validate_manuscript(
    latex: str,
    *,
    citation_map: dict[str, Any],
    figures_dir: str | None,
    plot_manifest: dict[str, Any] | None = None,
    plot_assets_index: dict[str, Any] | None = None,
    experimental_log_text: str | None = None,
    expected_section_titles: list[str] | None = None,
    narrative_plan: dict[str, Any] | None = None,
    claim_map: dict[str, Any] | None = None,
    citation_placement_plan: dict[str, Any] | None = None,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    issues.extend(check_prompt_meta_leakage(latex))
    issues.extend(check_unknown_citations(latex, citation_map))
    issues.extend(check_citation_coverage(latex, citation_map))
    issues.extend(check_figure_file_coverage(latex, figures_dir))
    issues.extend(check_plot_plan_coverage(latex, plot_manifest))
    issues.extend(check_generated_plot_asset_usage(latex, plot_assets_index))
    issues.extend(check_expected_section_substance(latex, expected_section_titles))
    issues.extend(check_numeric_grounding(latex, experimental_log_text))
    issues.extend(check_comparative_claims(latex, experimental_log_text))
    issues.extend(check_claim_map_coverage(latex, claim_map))
    issues.extend(check_citation_placement(latex, citation_placement_plan))
    issues.extend(check_narrative_section_roles(latex, narrative_plan))
    return issues
