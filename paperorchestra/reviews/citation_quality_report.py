from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

CITATION_QUALITY_GATE_SCHEMA_VERSION = "citation-quality-gate/2"
_PRIVATE_MARKERS = ("PRIVATE", "SECRET", "TOKEN")


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


def _citation_summary_from_items(items: list[CitationQualityItem]) -> dict[str, int]:
    summary = {"pass": 0, "weak": 0, "fail": 0, "human_needed": 0}
    for item in items:
        status = str(item.support_status or "unknown").strip().lower() or "unknown"
        if status == "supported" and not item.failing_codes:
            summary["pass"] += 1
        elif status == "metadata_only":
            summary["weak"] += 1
        elif status in {"unsupported", "contradicted"}:
            summary["fail"] += 1
        else:
            summary["human_needed"] += 1
    return summary


def _public_failures(items: list[CitationQualityItem], hard_gate_failures: list[str]) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    covered_codes: set[str] = set()
    for item in items:
        if not item.failing_codes:
            continue
        codes = [item.public_failure_code] if item.public_failure_code else list(item.failing_codes)
        for code in sorted(dict.fromkeys(code for code in codes if code)):
            covered_codes.add(code)
            failures.append(
                {
                    "case": str(item.public_case or item.claim_id or item.item_id),
                    "key": item.citation_key,
                    "code": str(code),
                    "message": str(item.public_failure_message or _default_public_failure_message(str(code))),
                }
            )
    item_internal_codes = {code for item in items for code in item.failing_codes}
    public_codes = {failure["code"] for failure in failures}
    for code in sorted(dict.fromkeys(hard_gate_failures)):
        if code in item_internal_codes or code in public_codes or code in covered_codes:
            continue
        failures.append({"case": "", "key": "", "code": str(code), "message": _default_public_failure_message(str(code))})
    return failures


def _default_public_failure_message(code: str) -> str:
    messages = {
        "human_needed": "Source requires manual evidence.",
        "critical_unsupported_citation": "Citation support is insufficient for a required claim.",
        "critical_citation_support_missing": "Citation support evidence is missing for a required claim.",
        "critical_unknown_reference": "A required citation has unknown rendered reference metadata.",
        "critical_missing_bib_entry": "A required citation is missing a rendered bibliography entry.",
        "critical_citation_metadata_missing": "Rendered citation metadata is unavailable for a required citation.",
        "critical_weak_reference_identity": "A required citation has weak reference identity.",
        "citation_quality_stale": "Citation quality evidence is stale for the current manuscript.",
        "citation_quality_manuscript_missing": "The manuscript is missing for citation quality evaluation.",
    }
    return messages.get(code, "Citation quality gate failed.")


def _assert_public_safe(payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    value_text = json.dumps(_public_values(payload), ensure_ascii=False, sort_keys=True)
    if any(marker in value_text.upper() for marker in _PRIVATE_MARKERS):
        raise ValueError("citation quality report contains a private marker")
    if re.search(r"/(?:tmp|home|root|Users)/", rendered):
        raise ValueError("citation quality report contains an absolute path")


def _public_values(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _public_values(item) for key, item in value.items() if key not in {"private_safe", "private_safe_summary"}}
    if isinstance(value, list):
        return [_public_values(item) for item in value]
    return value
