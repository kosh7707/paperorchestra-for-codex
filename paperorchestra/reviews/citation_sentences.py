from __future__ import annotations

import re
from typing import Any

from paperorchestra.manuscript.citation_key_parsing import CITE_COMMAND_RE
from paperorchestra.manuscript.citation_map_model import citation_entry_for_key


def _title_terms(title: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[A-Za-z0-9]{4,}", title)}


def _sentence_terms(sentence: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[A-Za-z0-9]{4,}", sentence)}


def _is_decimal_period(text: str, index: int) -> bool:
    return (
        text[index] == "."
        and index > 0
        and index + 1 < len(text)
        and text[index - 1].isdigit()
        and text[index + 1].isdigit()
    )


def _sentence_start(latex: str, cite_start: int) -> int:
    for idx in range(cite_start - 1, -1, -1):
        if latex[idx] in ".!?" and not _is_decimal_period(latex, idx):
            return idx + 1
        if latex[idx] == "\n" and idx > 0 and latex[idx - 1] == "\n":
            return idx + 1
    return 0


def _sentence_end(latex: str, cite_end: int) -> int:
    for idx in range(cite_end, len(latex)):
        if latex[idx] in ".!?" and not _is_decimal_period(latex, idx):
            return idx + 1
        if latex[idx] == "\n" and idx + 1 < len(latex) and latex[idx + 1] == "\n":
            return idx
    return len(latex)


def _citation_review_body(latex: str) -> str:
    r"""Return manuscript prose suitable for cited-sentence extraction.

    Citation support critics should judge author-facing claims, not LaTeX
    preamble/package/macro noise.  Keep citation commands intact so downstream
    key extraction still works, but remove non-prose regions that otherwise
    make the first cited span start at ``\documentclass``.
    """
    text = re.sub(r"(?<!\\)%.*", "", latex)
    begin = text.find(r"\begin{document}")
    if begin != -1:
        text = text[begin + len(r"\begin{document}") :]
    text = re.sub(r"\\end\{document\}.*\Z", "", text, flags=re.DOTALL)
    text = re.sub(r"\\begin\{thebibliography\}.*?\\end\{thebibliography\}", " ", text, flags=re.DOTALL)
    text = re.sub(r"\\bibliographystyle\{[^}]+\}|\\bibliography\{[^}]+\}", " ", text)
    text = re.sub(r"\\(?:title|author|date)\{[^}]*\}", " ", text, flags=re.DOTALL)
    text = re.sub(r"\\maketitle\b", " ", text)
    text = re.sub(r"\\(?:section|subsection|subsubsection)\*?\{([^}]+)\}", r"\n\n\1.\n\n", text)
    text = re.sub(r"\\begin\{(?:abstract|center|flushleft|flushright)\}|\\end\{(?:abstract|center|flushleft|flushright)\}", " ", text)
    text = re.sub(r"\\begin\{(?:table|table\*|figure|figure\*)\}.*?\\end\{(?:table|table\*|figure|figure\*)\}", " ", text, flags=re.DOTALL)
    text = re.sub(r"\\newcommand\{\\[A-Za-z]+\}(?:\[[^\]]+\])?\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", " ", text)
    return text


def _extract_cited_sentences(latex: str) -> list[str]:
    latex = _citation_review_body(latex)
    sentences: list[str] = []
    seen_spans: set[tuple[int, int]] = set()
    for match in CITE_COMMAND_RE.finditer(latex):
        start = _sentence_start(latex, match.start())
        end = _sentence_end(latex, match.end())
        span = (start, end)
        if span in seen_spans:
            continue
        seen_spans.add(span)
        sentence = latex[start:end]
        sentence = re.sub(r"^.*\\section\*?\{[^}]+\}\s*", "", sentence, flags=re.DOTALL)
        sentence = re.sub(r"\s+", " ", sentence).strip()
        if sentence:
            sentences.append(sentence)
    return sentences


def extract_cited_sentences(latex: str) -> list[str]:
    return _extract_cited_sentences(latex)


def _citation_keys_in_text(text: str) -> list[str]:
    keys: list[str] = []
    for match in CITE_COMMAND_RE.finditer(text):
        raw = match.group(2)
        keys.extend([item.strip() for item in raw.split(",") if item.strip()])
    return keys


def _citation_entry_payload(citation_map: dict[str, Any], keys: list[str]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for key in keys:
        entry = citation_entry_for_key(citation_map, key) if isinstance(citation_map, dict) else {}
        entries.append(
            {
                "key": key,
                "title": entry.get("title"),
                "authors": entry.get("authors"),
                "year": entry.get("year"),
                "venue": entry.get("venue"),
                "url": entry.get("url"),
                "doi": entry.get("doi"),
                "paper_id": entry.get("paper_id"),
                "provenance": entry.get("provenance"),
            }
        )
    return entries


