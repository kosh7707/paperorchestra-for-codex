from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from paperorchestra.loop_engine.quality.high_risk_claim_obligations import (
    _load_source_obligations_for_claim_sweep,
    _sentence_supported_by_obligation,
)
from paperorchestra.loop_engine.quality.high_risk_claim_patterns import (
    BENCHMARK_CLAIM_RE,
    HIGH_RISK_CLAIM_RE,
    LIMITATION_SCOPE_RE,
    PAPER_SPECIFIC_SELF_CLAIM_RE,
    PROOF_INTERNAL_SCOPE_RE,
    SECURITY_CLAIM_RE,
    STRUCTURAL_REFERENCE_RE,
    STRUCTURAL_STRONG_CLAIM_RE,
)
from paperorchestra.loop_engine.quality.high_risk_claim_sentences import (
    _clean_latex_sentence_for_claim_sweep,
    _plainish_sentences,
    _preserve_text_macro_arguments,
    _structural_boilerplate_sentence,
)


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
        if _structural_boilerplate_sentence(raw_sentence, sentence):
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


__all__ = [
    "BENCHMARK_CLAIM_RE",
    "HIGH_RISK_CLAIM_RE",
    "LIMITATION_SCOPE_RE",
    "PAPER_SPECIFIC_SELF_CLAIM_RE",
    "PROOF_INTERNAL_SCOPE_RE",
    "SECURITY_CLAIM_RE",
    "STRUCTURAL_REFERENCE_RE",
    "STRUCTURAL_STRONG_CLAIM_RE",
    "_clean_latex_sentence_for_claim_sweep",
    "_high_risk_claim_sweep",
    "_load_source_obligations_for_claim_sweep",
    "_plainish_sentences",
    "_preserve_text_macro_arguments",
    "_sentence_supported_by_obligation",
    "_structural_boilerplate_sentence",
]
