from __future__ import annotations

import re
from typing import Any

from paperorchestra.domains import get_domain
from paperorchestra.manuscript.citations import allowed_citation_keys, citation_entry_for_key
from paperorchestra.reviews.citation_sentences import (
    _citation_entry_payload,
    _citation_keys_in_text,
    _extract_cited_sentences,
    _sentence_terms,
    _title_terms,
)


def _claim_type(sentence: str) -> str:
    if re.search(r"\b\d+(?:\.\d+)?%?\b|\\times|\bfold\b", sentence, re.IGNORECASE):
        return "numeric"
    if re.search(r"outperform|state-of-the-art|faster|better|superior|improv", sentence, re.IGNORECASE):
        return "comparative"
    if re.search(r"is defined as|we define|definition|notion|model", sentence, re.IGNORECASE):
        return "definitional"
    if re.search(r"we use|we implement|pipeline|method|approach", sentence, re.IGNORECASE):
        return "method"
    return "background"


PAPER_SPECIFIC_SELF_CLAIM_RE = re.compile(
    r"\b("
    r"this\s+paper|we\s+(?:prove|show|construct|propose|implement|measure|report)|"
    r"our\s+(?:construction|scheme|method|proof|theorem|benchmark|result|evaluation|implementation)|"
    r"(?:proposed|presented|evaluated)\s+(?:construction|scheme|method|proof|benchmark|result)"
    r")\b",
    re.IGNORECASE,
)


PAPER_SPECIFIC_TOPIC_RE = get_domain().paper_specific_topic_re


EXTERNAL_BACKGROUND_RE = re.compile(
    r"\b(prior|previous|existing|related\s+work|standard|protocol|systems?|literature|baseline|background)\b",
    re.IGNORECASE,
)


def _mixed_paper_specific_citation_scope(sentence: str) -> bool:
    """Return true when one cited sentence uses an external citation to carry
    both background and this-paper-specific method/proof/result claims.

    The detector is deliberately conservative: it only fires for cited
    sentences that contain both external-background framing and paper-specific
    construction/proof/benchmark/result language. Pure background citations and
    uncited authorial claims are left to their existing gates.
    """

    return bool(
        _citation_keys_in_text(sentence)
        and PAPER_SPECIFIC_SELF_CLAIM_RE.search(sentence)
        and PAPER_SPECIFIC_TOPIC_RE.search(sentence)
        and EXTERNAL_BACKGROUND_RE.search(sentence)
    )


def _paper_specific_external_citation_scope(sentence: str) -> bool:
    """Return true when an external citation appears to support this paper's
    own proof/method/result claim.

    Pure uncited authorial claims are handled by claim-safety policy and pure
    background citations should remain valid.  The citation-support critic only
    fires here when a cited sentence itself contains first-party paper-specific
    language plus method/proof/benchmark/result topics.
    """

    return bool(
        _citation_keys_in_text(sentence)
        and PAPER_SPECIFIC_SELF_CLAIM_RE.search(sentence)
        and PAPER_SPECIFIC_TOPIC_RE.search(sentence)
    )


def _heuristic_citation_items(latex: str, citation_map: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for idx, sentence in enumerate(_extract_cited_sentences(latex), start=1):
        keys = []
        keys = _citation_keys_in_text(sentence)
        unknown = [key for key in keys if key not in allowed_citation_keys(citation_map)]
        overlaps = []
        sentence_terms = _sentence_terms(sentence)
        for key in keys:
            entry = citation_entry_for_key(citation_map, key) if isinstance(citation_map, dict) else {}
            title = entry.get("title", "") if isinstance(entry, dict) else ""
            overlap = sorted(sentence_terms & _title_terms(title))
            if overlap:
                overlaps.append({"key": key, "overlap_terms": overlap[:5]})
        comparative = bool(re.search(r"outperform|state-of-the-art|faster|better|superior", sentence, re.IGNORECASE))
        mixed_scope_violation = _mixed_paper_specific_citation_scope(sentence)
        paper_specific_scope_violation = _paper_specific_external_citation_scope(sentence)
        flags: list[str] = []
        if mixed_scope_violation:
            flags.append("mixed_paper_specific_citation_scope")
        elif paper_specific_scope_violation:
            flags.append("paper_specific_external_citation_scope")
        if mixed_scope_violation or paper_specific_scope_violation:
            status = "unsupported"
            risk = "high"
            fix = (
                "Split the sentence or remove the external citation from this paper's own method/proof/result claim; "
                "external citations may support background, while paper-specific claims need internal references, "
                "source-material evidence, or uncited authorial framing."
            )
        elif unknown:
            status = "unsupported"
            risk = "high"
            fix = "Replace unknown citation keys with imported/verified citation_map entries."
        elif comparative and not overlaps:
            status = "weakly_supported"
            risk = "medium"
            fix = "Ensure the cited work directly supports the comparative claim or narrow the claim."
        elif overlaps:
            status = "metadata_only"
            risk = "medium"
            fix = "Title/metadata overlap is only advisory; run a model/web citation-support critic or manually verify source support."
        else:
            status = "insufficient_evidence"
            risk = "medium"
            fix = "No direct support evidence was collected; run a model/web citation-support critic or manually confirm the cited source supports this sentence."
        items.append(
            {
                "id": f"cite-{idx:03d}",
                "sentence": sentence,
                "citation_keys": keys,
                "citation_entries": _citation_entry_payload(citation_map, keys),
                "claim_type": _claim_type(sentence),
                "support_status": status,
                "heuristic_support_status": status,
                "risk": risk,
                "heuristic_risk": risk,
                "critic_source": "heuristic",
                "evidence_strength": "metadata_only" if status == "metadata_only" else "none",
                "evidence_overlap": overlaps,
                "evidence": [],
                "suggested_fix": fix,
                "flags": flags,
            }
        )
    return items


def _summary_from_items(items: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for item in items:
        status = str(item.get("support_status") or "needs_manual_check")
        summary[status] = summary.get(status, 0) + 1
    return summary


