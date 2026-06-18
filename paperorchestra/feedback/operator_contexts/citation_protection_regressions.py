from __future__ import annotations

from typing import Any

from paperorchestra.feedback.operator_contract import _read_packet
from paperorchestra.feedback.operator_contexts.citation_protection_supported import (
    _protected_item_text,
    _protected_supported_citation_context,
)
from paperorchestra.feedback.operator_contexts.packet import _packet_payload_by_role
from paperorchestra.feedback.operator_contexts.text import _normalized_context_text


def _protected_supported_citation_regressions(
    imported: dict[str, Any],
    candidate_text: str,
    *,
    limit: int = 24,
) -> list[dict[str, Any]]:
    packet_path = imported.get("packet_path")
    if not packet_path:
        return []
    try:
        packet = _read_packet(packet_path)
    except Exception:
        return []
    citation_review = _packet_payload_by_role(packet, "citation_support_review")
    citation_integrity_audit = _packet_payload_by_role(packet, "citation_integrity_audit")
    protected = _protected_supported_citation_context(
        citation_review,
        citation_integrity_audit,
        limit=10_000,
    )
    if not isinstance(protected, list) or not protected:
        return []
    normalized_candidate = _normalized_context_text(candidate_text)
    regressions: list[dict[str, Any]] = []
    for item in protected:
        if not isinstance(item, dict):
            continue
        text = _protected_item_text(item)
        if not text or text in normalized_candidate:
            continue
        compact = {
            "id": str(item.get("id") or ""),
            "citation_keys": [str(key) for key in item.get("citation_keys") or [] if str(key).strip()],
        }
        if item.get("source_shape"):
            compact["source_shape"] = str(item.get("source_shape"))
        regressions.append(compact)
        if len(regressions) >= limit:
            break
    return regressions
