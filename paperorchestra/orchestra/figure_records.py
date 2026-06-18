from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

FIGURE_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".svg"}
FIGURE_GATE_SCHEMA_VERSION = "figure-gate-report/1"
FIGURE_GATE_REPORT_FILENAME = "figure_gate.report.json"

_PRIVATE_MARKERS = ("PRIVATE", "SECRET", "TOKEN", "KEY", "UNDER_REVIEW")
_SAFE_SLOT_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,47}$")


@dataclass(frozen=True)
class FigureAsset:
    path: str
    filename: str
    sha256: str

    def to_public_dict(self) -> dict[str, str]:
        return {
            "asset_label": _redacted_label("figure-asset", f"{self.filename}:{self.sha256}"),
            "sha256": self.sha256,
            "extension": Path(self.filename).suffix.lower(),
        }


@dataclass(frozen=True)
class FigureInventory:
    assets: list[FigureAsset] = field(default_factory=list)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "figure-inventory/1",
            "asset_count": len(self.assets),
            "assets": [asset.to_public_dict() for asset in self.assets],
        }


@dataclass(frozen=True)
class FigureSlot:
    slot_id: str
    purpose: str
    placeholder: bool = True

    def public_id(self) -> str:
        if _is_public_safe_identifier(self.slot_id):
            return self.slot_id
        return _redacted_label("figure-slot", self.slot_id)


@dataclass(frozen=True)
class GeneratedFigureAvailability:
    figure_id: str
    sha256: str
    reasons: tuple[str, ...] = ("generated_asset_available", "generated_placeholder", "human_final_artwork_required")


@dataclass(frozen=True)
class FigureMatchDecision:
    slot_id: str
    status: str
    asset_filename: str | None = None
    reasons: list[str] = field(default_factory=list)
    selected_asset_sha256: str | None = None
    candidate_asset_count: int = 0
    replacement_proposed: bool = False
    replacement_applied: bool = False

    def to_public_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "slot_id": self.slot_id if _is_public_safe_identifier(self.slot_id) else _redacted_label("figure-slot", self.slot_id),
            "status": self.status,
            "private_safe": True,
            "reasons": list(self.reasons),
            "candidate_asset_count": self.candidate_asset_count,
            "replacement_proposed": self.replacement_proposed,
            "replacement_applied": self.replacement_applied,
        }
        if self.selected_asset_sha256:
            payload["selected_asset_sha256"] = self.selected_asset_sha256
        if self.asset_filename:
            payload["asset_label"] = _redacted_label("figure-asset", f"{self.asset_filename}:{self.selected_asset_sha256 or ''}")
        return payload


@dataclass(frozen=True)
class FigureGateReport:
    status: str
    decisions: list[FigureMatchDecision]
    blocking_reasons: list[str] = field(default_factory=list)

    def to_public_dict(self) -> dict[str, Any]:
        summary = _decision_summary(self.decisions)
        return {
            "schema_version": FIGURE_GATE_SCHEMA_VERSION,
            "status": self.status,
            "private_safe_summary": True,
            "summary": summary,
            "decisions": [decision.to_public_dict() for decision in self.decisions],
            "blocking_reasons": list(dict.fromkeys(self.blocking_reasons)),
            "acceptance_gate_impacts": {
                "supplied_figures_inventoried_matched_or_blocked": "pass" if self.status == "pass" else "blocked",
                "figure_replacements_applied": "not_applied_by_gate",
            },
            "replacement_policy": {
                "replacement_applied_by_this_gate": False,
                "detail": "This gate proposes deterministic figure matches only; it never mutates TeX/PDF artifacts.",
            },
        }


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _redacted_label(kind: str, value: str) -> str:
    return f"redacted-{kind}:{_sha256_text(value)[:12]}"


def _contains_private_marker(value: str) -> bool:
    upper = value.upper()
    return any(marker in upper for marker in _PRIVATE_MARKERS)


def _is_public_safe_identifier(value: str) -> bool:
    return bool(_SAFE_SLOT_ID_RE.fullmatch(value)) and not _contains_private_marker(value)


def _decision_summary(decisions: list[FigureMatchDecision]) -> dict[str, int]:
    summary = {
        "matched": 0,
        "generated_asset_available": 0,
        "ambiguous": 0,
        "missing": 0,
        "human_finalization_needed": 0,
    }
    for decision in decisions:
        if decision.status in summary:
            summary[decision.status] += 1
        if decision.status in {"ambiguous", "missing", "human_finalization_needed"}:
            summary["human_finalization_needed"] += 1
    summary["total"] = len(decisions)
    return summary
