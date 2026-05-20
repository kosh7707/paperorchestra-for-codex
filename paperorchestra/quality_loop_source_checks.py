from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .domains import detect_domain_for_text, get_domain
from .quality_loop_utils import _read_json_if_exists
from .validator import check_citation_placement, check_claim_map_coverage, check_narrative_section_roles, extract_decimal_like_tokens


HIGH_RISK_CLAIM_RE = get_domain().high_risk_claim_re
LIMITATION_SCOPE_RE = re.compile(
    r"\b("
    r"do not claim|does not claim|does not make (?:stronger )?(?:analytical )?claims?|not claim|limited to|only|scope|limitations?|omits?|not end-to-end|we do not|we leave|future work|"
    r"do not support claims?|does not support claims?|do not support (?:any )?claim|does not support (?:any )?claim|"
    r"does not guarantee|do not guarantee|no guarantee|cannot guarantee|"
    r"contains no (?:external )?(?:dataset|benchmark|evaluation|experiment)|"
    r"includes no (?:external )?(?:dataset|benchmark|evaluation|experiment)|"
    r"reports no (?:standard )?(?:benchmark|metric|runtime|comparison)|"
    r"no standard benchmark|no optimizer setting|no model-architecture comparison|no reported runtime profile|"
    r"outside (?:the )?(?:present )?scope|beyond (?:the )?(?:present )?scope|"
    r"remain(?:s)? within the stated assumptions|bounded by the stated assumptions|"
    r"stronger analytical claims require|separate argument beyond|"
    r"should therefore be read within"
    r")\b",
    re.IGNORECASE,
)
SECURITY_CLAIM_RE = get_domain().security_claim_re
BENCHMARK_CLAIM_RE = get_domain().benchmark_claim_re
PROOF_INTERNAL_SCOPE_RE = re.compile(
    r"\b(we now examine|conditioned game|proof proceeds|combining the game hops|union bound over|the proof proceeds)\b",
    re.IGNORECASE,
)
PAPER_SPECIFIC_SELF_CLAIM_RE = re.compile(
    r"\b("
    r"this\s+paper|we\s+(?:prove|show|construct|propose|implement|measure|report)|"
    r"our\s+(?:construction|scheme|method|proof|theorem|benchmark|result|evaluation|implementation)|"
    r"(?:proposed|presented|evaluated)\s+(?:construction|scheme|method|proof|benchmark|result)"
    r")\b",
    re.IGNORECASE,
)

def _read_text_if_exists(path: str | Path | None) -> str:
    if not path:
        return ""
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return ""
    return candidate.read_text(encoding="utf-8", errors="replace")

def _source_material_fidelity_check(state) -> dict[str, Any]:
    paper_text = _read_text_if_exists(state.artifacts.paper_full_tex)
    source_parts = [
        _read_text_if_exists(state.inputs.idea_path),
        _read_text_if_exists(state.inputs.experimental_log_path),
        _read_text_if_exists(state.inputs.template_path),
    ]
    source_text = "\n".join(part for part in source_parts if part)
    domain = detect_domain_for_text(source_text)
    lowered_source = source_text.lower()
    lowered_paper = paper_text.lower()

    proof_required = bool(domain.proof_seed_re.search(lowered_source) or re.search(r"\btheorem\b.*\bproof\b", lowered_source, re.IGNORECASE | re.DOTALL))
    proof_present = bool(
        re.search(
            r"\\begin\{(?:theorem|lemma|proof|proposition)\}|\b(proof|theorem|analysis|bound|guarantee)\b|\\section\*?\{[^}]*(?:security|analysis|proof)[^}]*\}",
            lowered_paper,
            re.IGNORECASE | re.DOTALL,
        )
    )
    benchmark_required = bool(domain.benchmark_seed_re.search(source_text))
    source_numbers = extract_decimal_like_tokens(source_text)
    paper_numbers = extract_decimal_like_tokens(paper_text)
    result_numbers_preserved = sorted(source_numbers & paper_numbers)
    results_present = not (benchmark_required and source_numbers) or bool(result_numbers_preserved)

    failing_codes: list[str] = []
    if proof_required and not proof_present:
        failing_codes.append("source_material_proof_omitted")
    if not results_present:
        failing_codes.append("source_material_results_omitted")
    return {
        "status": "fail" if failing_codes else "pass",
        "failing_codes": failing_codes,
        "proof_required": proof_required,
        "proof_present": proof_present,
        "benchmark_required": benchmark_required,
        "source_numeric_token_count": len(source_numbers),
        "preserved_numeric_tokens": result_numbers_preserved,
        "source_material_paths": {
            "idea": state.inputs.idea_path,
            "experimental_log": state.inputs.experimental_log_path,
            "template": state.inputs.template_path,
        },
    }

def _planning_satisfaction_check(state, planning_status: dict[str, Any]) -> dict[str, Any]:
    if planning_status.get("status") != "pass" or not state.artifacts.paper_full_tex or not Path(state.artifacts.paper_full_tex).exists():
        return {"status": "skipped", "failing_codes": [], "reason": "planning artifacts unavailable or manuscript missing"}
    latex = Path(state.artifacts.paper_full_tex).read_text(encoding="utf-8", errors="replace")
    payloads = planning_status.get("payloads") if isinstance(planning_status.get("payloads"), dict) else {}
    issues = []
    issues.extend(check_claim_map_coverage(latex, payloads.get("claim_map")))
    issues.extend(check_citation_placement(latex, payloads.get("citation_placement_plan")))
    issues.extend(check_narrative_section_roles(latex, payloads.get("narrative_plan")))
    failing_codes = sorted({issue.code for issue in issues if issue.severity == "error"})
    return {
        "status": "fail" if failing_codes else "pass",
        "failing_codes": failing_codes,
        "issue_count": len(issues),
        "issues": [issue.to_dict() for issue in issues],
    }

def _preserve_text_macro_arguments(text: str) -> str:
    text_macros = {
        "emph",
        "textbf",
        "textit",
        "textrm",
        "textsf",
        "texttt",
        "underline",
        "mbox",
        "paragraph",
        "subparagraph",
    }
    pattern = re.compile(r"\\([A-Za-z]+)\*?(?:\[[^]]*\])?\{([^{}]*)\}")
    previous = None
    while previous != text:
        previous = text
        text = pattern.sub(lambda match: match.group(2) if match.group(1) in text_macros else " ", text)
    return text


def _clean_latex_sentence_for_claim_sweep(text: str) -> str:
    text = re.sub(r"(?m)%.*$", " ", text)
    text = re.sub(r"\\(?:label|ref|eqref|cite)\{[^}]*\}", " ", text)
    text = re.sub(r"\\(?:begin|end)\{[^}]*\}", " ", text)
    text = re.sub(r"\\(?:section|subsection|subsubsection)\*?\{([^}]*)\}", r"\1. ", text)
    text = _preserve_text_macro_arguments(text)
    text = re.sub(r"\\[A-Za-z]+\*?(?:\[[^]]*\])?(?:\{[^}]*\})?", " ", text)
    text = re.sub(r"[$^_{}&]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _plainish_sentences(latex: str) -> list[tuple[int, str, str]]:
    document_start = re.search(r"\\begin\{document\}", latex)
    base_line_offset = 0
    body = latex
    if document_start:
        base_line_offset = latex[: document_start.end()].count("\n")
        body = latex[document_start.end() :]
    without_comments = re.sub(r"(?m)%.*$", "", body)
    rough = re.split(r"(?<=[.!?])\s+|\n\s*\n", without_comments)
    result: list[tuple[int, str, str]] = []
    offset = 0
    for part in rough:
        offset = without_comments.find(part, offset)
        line = base_line_offset + without_comments[: max(offset, 0)].count("\n") + 1
        raw_text = part.strip()
        text = _clean_latex_sentence_for_claim_sweep(part)
        if len(text) >= 35 and re.search(r"[A-Za-z]{3,}", text):
            result.append((line, raw_text, text))
        offset += max(len(part), 1)
    return result

def _sentence_supported_by_obligation(sentence: str, obligation: dict[str, Any]) -> bool:
    lowered = sentence.lower()
    obligation_type = str(obligation.get("type") or "")
    if SECURITY_CLAIM_RE.search(sentence) and obligation_type not in {
        "security_assumption",
        "theorem_or_bound",
        "proof_step",
        "method_core",
    }:
        return False
    if BENCHMARK_CLAIM_RE.search(sentence) and obligation_type not in {"benchmark_setup", "benchmark_result"}:
        return False
    terms = [str(term).lower() for term in obligation.get("required_terms") or [] if str(term).strip()]
    matched_terms = [term for term in terms if term in lowered]
    required_min = min(len(terms), max(1, 2 if len(terms) >= 3 else len(terms)))
    if len(matched_terms) < required_min:
        return False
    sentence_numbers = extract_decimal_like_tokens(sentence)
    obligation_numbers = {str(token) for token in obligation.get("numeric_tokens") or []}
    if (obligation_type == "benchmark_result" or sentence_numbers) and obligation_numbers:
        return bool(sentence_numbers & obligation_numbers)
    return True

def _load_source_obligations_for_claim_sweep(source_obligations: dict[str, Any]) -> list[dict[str, Any]]:
    """Load usable source obligations even when the coverage check is partially failing.

    ``evaluate_source_obligations`` can fail because one obligation is missing
    from a candidate manuscript.  Treating that as an all-or-nothing signal made
    the high-risk sweep discard every other still-valid author-material
    obligation, causing one local repair regression to cascade into dozens of
    spurious ``high_risk_uncited_claim`` findings.  The sweep only needs the
    obligation matrix to decide whether a sentence is grounded in supplied
    material, so it may use the current, schema-valid matrix unless the matrix
    itself is missing, stale, or legacy/untrusted.
    """
    if not isinstance(source_obligations, dict):
        return []
    failing_codes = {str(code) for code in source_obligations.get("failing_codes") or []}
    if failing_codes & {
        "source_obligations_missing",
        "source_obligations_stale",
        "source_obligations_legacy_untrusted",
    }:
        return []
    payload = _read_json_if_exists(source_obligations.get("path"))
    if not isinstance(payload, dict):
        return []
    return [obligation for obligation in payload.get("obligations") or [] if isinstance(obligation, dict)]

def _high_risk_claim_sweep(state, source_obligations: dict[str, Any]) -> dict[str, Any]:
    if not state.artifacts.paper_full_tex or not Path(state.artifacts.paper_full_tex).exists():
        return {"status": "skipped", "failing_codes": [], "reason": "paper_full_tex_missing", "items": []}
    latex = Path(state.artifacts.paper_full_tex).read_text(encoding="utf-8", errors="replace")
    satisfied_obligations = _load_source_obligations_for_claim_sweep(source_obligations)
    items: list[dict[str, Any]] = []
    for line, raw_sentence, sentence in _plainish_sentences(latex):
        if len(sentence) < 35:
            continue
        if "\\bibliography" in raw_sentence or "\\bibitem" in raw_sentence:
            continue
        if "\\cite" in raw_sentence and not PAPER_SPECIFIC_SELF_CLAIM_RE.search(sentence):
            continue
        if re.match(r"\s*\\(?:section|subsection|paragraph)\b", sentence):
            continue
        if LIMITATION_SCOPE_RE.search(sentence):
            continue
        if PROOF_INTERNAL_SCOPE_RE.search(sentence):
            continue
        if not HIGH_RISK_CLAIM_RE.search(sentence):
            continue
        supporting_obligation = next(
            (obligation for obligation in satisfied_obligations if _sentence_supported_by_obligation(sentence, obligation)),
            None,
        )
        if supporting_obligation is not None:
            continue
        items.append(
            {
                "line": line,
                "sentence": sentence[:300],
                "reason": "high-risk factual/novelty/security/numeric claim lacks citation, source-obligation support, or limitation scoping",
            }
        )
    return {
        "status": "fail" if items else "pass",
        "failing_codes": ["high_risk_uncited_claim"] if items else [],
        "items": items,
        "item_count": len(items),
    }
