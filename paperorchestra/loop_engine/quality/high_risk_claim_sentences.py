from __future__ import annotations

import re

from paperorchestra.loop_engine.quality.high_risk_claim_patterns import STRUCTURAL_REFERENCE_RE, STRUCTURAL_STRONG_CLAIM_RE


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


def _structural_boilerplate_sentence(raw_sentence: str, sentence: str) -> bool:
    raw = raw_sentence.strip()
    if re.match(r"\\(?:title|author|date)\*?(?:\[[^]]*\])?\{", raw):
        return True
    if "\\caption" in raw:
        return not STRUCTURAL_STRONG_CLAIM_RE.search(sentence)
    if STRUCTURAL_REFERENCE_RE.search(sentence):
        return not STRUCTURAL_STRONG_CLAIM_RE.search(sentence)
    return False
