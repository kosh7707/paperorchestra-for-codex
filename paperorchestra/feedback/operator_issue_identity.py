from __future__ import annotations

import re

from paperorchestra.feedback.packet_artifacts import _canonical_sha256, _sha256_bytes


def _normalize_issue_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def derive_operator_issue_id(
    packet_sha256: str,
    *,
    source_artifact_role: str,
    source_item_key: str,
    target_section: str,
    rationale: str,
    suggested_action: str,
) -> str:
    issue_text = _normalize_issue_text(f"{rationale}\n{suggested_action}")
    payload = {
        "packet_sha256": packet_sha256,
        "source_artifact_role": source_artifact_role,
        "source_item_key": source_item_key,
        "target_section": target_section,
        "issue_text_sha256": _sha256_bytes(issue_text.encode("utf-8")),
    }
    return "opfb-" + _canonical_sha256(payload)[:20]


__all__ = ["_normalize_issue_text", "derive_operator_issue_id"]
