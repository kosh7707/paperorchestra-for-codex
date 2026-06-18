from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from paperorchestra.core.models import utc_now_iso
from paperorchestra.core.session import load_session
from paperorchestra.manuscript.source_obligation_extraction import (
    OBLIGATION_SOURCE_LABELS,
    _candidate_excerpts,
    _expected_area,
    _sha256_text,
    _source_packet,
    _substantive_word_count,
    _terms,
    obligation_domains_for_text,
)
from paperorchestra.manuscript.validator import extract_decimal_like_tokens

SOURCE_OBLIGATIONS_SCHEMA_VERSION = "source-obligations/1"


def build_source_obligations(cwd: str | Path | None) -> dict[str, Any]:
    state = load_session(cwd)
    source_entries, packet_digest, texts = _source_packet(cwd)
    obligations: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for label, text in texts.items():
        if not text.strip():
            continue
        domain = obligation_domains_for_text(text)
        if label not in OBLIGATION_SOURCE_LABELS:
            continue
        for obligation_type, raw_pattern, seed_terms in domain.obligation_patterns:
            pattern = re.compile(raw_pattern, re.IGNORECASE)
            for excerpt in _candidate_excerpts(label, text, pattern):
                if _substantive_word_count(excerpt) < 6:
                    continue
                key = (obligation_type, _sha256_text(excerpt)[:16])
                if key in seen:
                    continue
                seen.add(key)
                numeric_tokens = sorted(extract_decimal_like_tokens(excerpt))
                obligation_id = f"obl-{len(obligations)+1:03d}-{obligation_type}"
                obligations.append(
                    {
                        "id": obligation_id,
                        "type": obligation_type,
                        "source_label": label,
                        "source_path": getattr(state.inputs, f"{label}_path", None) if label != "experimental_log" else state.inputs.experimental_log_path,
                        "source_packet_sha256": packet_digest,
                        "excerpt_sha256": _sha256_text(excerpt),
                        "excerpt_preview": excerpt[:240],
                        "required_terms": _terms(excerpt, seed_terms),
                        "numeric_tokens": numeric_tokens,
                        "expected_manuscript_area": _expected_area(obligation_type),
                    }
                )
    return {
        "schema_version": SOURCE_OBLIGATIONS_SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "session_id": state.session_id,
        "source_packet_sha256": packet_digest,
        "source_files": source_entries,
        "generator": {
            "name": "paperorchestra.deterministic_source_obligations",
            "version": 1,
            "model_used": False,
        },
        "obligations": obligations,
    }
