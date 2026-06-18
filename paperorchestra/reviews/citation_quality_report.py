from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from paperorchestra.reviews.citation_quality_public import (
    _assert_public_safe,
    _citation_summary_from_items,
    _default_public_failure_message,
    _public_failures,
    _public_values,
)

CITATION_QUALITY_GATE_SCHEMA_VERSION = "citation-quality-gate/2"

@dataclass(frozen=True)
class CitationQualityItem:
    item_id: str
    citation_key: str
    claim_id: str | None
    citation_key_sha256: str
    critical: bool
    need_status: str
    support_status: str
    metadata_status: str
    severity: str
    failing_codes: list[str] = field(default_factory=list)
    warning_codes: list[str] = field(default_factory=list)
    public_case: str | None = None
    public_failure_code: str | None = None
    public_failure_message: str | None = None
    private_safe: bool = True

    def to_internal_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "claim_id": self.claim_id,
            "citation_keys_sha256": [self.citation_key_sha256],
            "critical": self.critical,
            "need_status": self.need_status,
            "support_status": self.support_status,
            "metadata_status": self.metadata_status,
            "severity": self.severity,
            "failing_codes": list(self.failing_codes),
            "warning_codes": list(self.warning_codes),
            "private_safe": self.private_safe,
        }


@dataclass(frozen=True)
class CitationQualityGateReport:
    status: str
    quality_mode: str
    manuscript_sha256: str | None
    hard_gate_failures: list[str]
    warning_codes: list[str]
    counts: dict[str, int]
    items: list[CitationQualityItem] = field(default_factory=list)
    source_artifact_hashes: dict[str, str | None] = field(default_factory=dict)
    private_safe_summary: bool = True

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "schema": CITATION_QUALITY_GATE_SCHEMA_VERSION,
            "status": self.status,
            "summary": _citation_summary_from_items(self.items),
            "failures": _public_failures(self.items, self.hard_gate_failures),
        }

    def to_internal_dict(self) -> dict[str, Any]:
        hard = sorted(dict.fromkeys(self.hard_gate_failures))
        warnings = sorted(dict.fromkeys(self.warning_codes))
        gate_summary = {
            "status": self.status,
            "hard_failures": len(hard),
            "warnings": len(warnings),
            "critical_needs": int(self.counts.get("critical_need_count") or 0),
            "critical_unsupported": int(self.counts.get("critical_unsupported_count") or 0),
        }
        citation_summary = _citation_summary_from_items(self.items)
        return {
            "schema": CITATION_QUALITY_GATE_SCHEMA_VERSION,
            "schema_version": CITATION_QUALITY_GATE_SCHEMA_VERSION,
            "public_report": self.to_public_dict(),
            "status": self.status,
            "quality_mode": self.quality_mode,
            "summary": citation_summary,
            "gate_summary": gate_summary,
            "failures": _public_failures(self.items, self.hard_gate_failures),
            "manuscript_sha256": self.manuscript_sha256,
            "hard_gate_failures": hard,
            "warning_codes": warnings,
            "counts": dict(self.counts),
            "items": [item.to_internal_dict() for item in self.items],
            "acceptance_gate_impacts": {
                "no_unknown_refs_for_critical_claims": "fail"
                if any(code in hard for code in {"critical_unknown_reference", "critical_missing_bib_entry"})
                else "pass",
                "citation_integrity": "fail" if hard else ("warn" if warnings else "pass"),
            },
            "source_artifact_hashes": dict(self.source_artifact_hashes),
            "private_safe_summary": self.private_safe_summary,
        }
