from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .io_utils import write_json
from .orchestra_policies import ReadinessPolicy
from .orchestra_state import OrchestraState
from .session import artifact_path, load_session

FIGURE_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".svg"}
FIGURE_GATE_SCHEMA_VERSION = "figure-gate-report/1"
FIGURE_GATE_REPORT_FILENAME = "figure_gate.report.json"

_PRIVATE_MARKERS = ("PRIVATE", "SECRET", "TOKEN", "KEY", "UNDER_REVIEW")
_SAFE_SLOT_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,47}$")
_STOPWORDS = {
    "and",
    "for",
    "from",
    "into",
    "the",
    "this",
    "that",
    "with",
    "figure",
    "fig",
    "plot",
    "image",
    "diagram",
    "placeholder",
    "generated",
    "overview",
}


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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _redacted_label(kind: str, value: str) -> str:
    return f"redacted-{kind}:{_sha256_text(value)[:12]}"


def _contains_private_marker(value: str) -> bool:
    upper = value.upper()
    return any(marker in upper for marker in _PRIVATE_MARKERS)


def _is_public_safe_identifier(value: str) -> bool:
    return bool(_SAFE_SLOT_ID_RE.fullmatch(value)) and not _contains_private_marker(value)


def _read_json_if_exists(path: str | Path | None) -> Any:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists():
        return None
    return json.loads(candidate.read_text(encoding="utf-8"))


def _decision_summary(decisions: list[FigureMatchDecision]) -> dict[str, int]:
    summary = {"matched": 0, "ambiguous": 0, "missing": 0, "human_finalization_needed": 0}
    for decision in decisions:
        if decision.status in summary:
            summary[decision.status] += 1
        if decision.status in {"ambiguous", "missing", "human_finalization_needed"}:
            summary["human_finalization_needed"] += 1
    summary["total"] = len(decisions)
    return summary


def figure_gate_report_path(cwd: str | Path | None = None) -> Path:
    return artifact_path(cwd, FIGURE_GATE_REPORT_FILENAME)


def inventory_figure_assets(root: str | Path) -> FigureInventory:
    base = Path(root)
    assets = [
        FigureAsset(path=str(path), filename=path.name, sha256=_sha256(path))
        for path in sorted(base.rglob("*"))
        if path.is_file() and path.suffix.lower() in FIGURE_EXTENSIONS
    ]
    return FigureInventory(assets=assets)


class FigureGatePolicy:
    def match_slot(self, slot: FigureSlot, assets: list[FigureAsset]) -> FigureMatchDecision:
        purpose_tokens = self._tokens(slot.purpose)
        if not slot.placeholder:
            return FigureMatchDecision(slot_id=slot.slot_id, status="already_realized", reasons=["slot_is_not_placeholder"])
        if not purpose_tokens:
            return FigureMatchDecision(
                slot_id=slot.slot_id,
                status="missing",
                reasons=["figure_slot_purpose_missing"],
            )
        scored: list[tuple[int, FigureAsset]] = []
        for asset in assets:
            filename_tokens = self._tokens(Path(asset.filename).stem)
            score = len(purpose_tokens & filename_tokens)
            if score > 0:
                scored.append((score, asset))
        if not scored:
            return FigureMatchDecision(
                slot_id=slot.slot_id,
                status="missing",
                reasons=["figure_asset_missing"],
            )
        threshold = min(2, len(purpose_tokens))
        best_score = max(score for score, _asset in scored)
        candidates = [asset for score, asset in scored if score == best_score and score >= threshold]
        if not candidates:
            return FigureMatchDecision(
                slot_id=slot.slot_id,
                status="missing",
                candidate_asset_count=len(scored),
                reasons=["figure_asset_missing"],
            )
        if len(candidates) > 1:
            return FigureMatchDecision(
                slot_id=slot.slot_id,
                status="ambiguous",
                candidate_asset_count=len(candidates),
                reasons=["multiple_plausible_figure_matches"],
            )
        asset = candidates[0]
        return FigureMatchDecision(
            slot_id=slot.slot_id,
            status="matched",
            asset_filename=asset.filename,
            selected_asset_sha256=asset.sha256,
            candidate_asset_count=1,
            replacement_proposed=True,
            replacement_applied=False,
            reasons=["safe_token_match"],
        )

    def apply_to_state(self, state: OrchestraState) -> OrchestraState:
        updated = state.clone()
        if updated.facets.figures == "placeholder_only" and "placeholder_figure_unresolved" not in updated.blocking_reasons:
            updated.blocking_reasons.append("placeholder_figure_unresolved")
        return ReadinessPolicy().apply(updated)

    def _tokens(self, text: str) -> set[str]:
        normalized = re.sub(r"[^a-zA-Z0-9]+", " ", text.lower())
        return {token for token in normalized.split() if len(token) > 2 and token not in _STOPWORDS}


def _slot_from_mapping(item: dict[str, Any], *, fallback_index: int, default_placeholder: bool) -> FigureSlot | None:
    identifier = item.get("figure_id") or item.get("id") or item.get("label") or item.get("filename") or f"figure_slot_{fallback_index}"
    purpose = item.get("purpose") or item.get("caption") or item.get("title") or item.get("description") or identifier
    placeholder_value = item.get("placeholder")
    if placeholder_value is None:
        placeholder = bool(
            default_placeholder
            or item.get("asset_kind") == "generated_placeholder"
            or item.get("review_status") == "human_final_artwork_required"
        )
    else:
        placeholder = bool(placeholder_value)
    if not isinstance(identifier, str) or not isinstance(purpose, str):
        return None
    return FigureSlot(slot_id=identifier, purpose=purpose, placeholder=placeholder)


def derive_figure_slots(
    *,
    plot_assets_path: str | Path | None = None,
    plot_manifest_path: str | Path | None = None,
    plot_captions_path: str | Path | None = None,
) -> list[FigureSlot]:
    slots: list[FigureSlot] = []
    seen: set[str] = set()

    def append(slot: FigureSlot | None) -> None:
        if slot is None:
            return
        key = slot.slot_id
        if key in seen:
            return
        seen.add(key)
        slots.append(slot)

    assets_payload = _read_json_if_exists(plot_assets_path)
    if isinstance(assets_payload, dict):
        for index, item in enumerate(assets_payload.get("assets") or [], start=1):
            if not isinstance(item, dict):
                continue
            if item.get("asset_kind") == "generated_placeholder" or item.get("review_status") == "human_final_artwork_required":
                append(_slot_from_mapping(item, fallback_index=index, default_placeholder=True))

    manifest_payload = _read_json_if_exists(plot_manifest_path)
    if isinstance(manifest_payload, dict):
        for index, item in enumerate(manifest_payload.get("figures") or [], start=1):
            if isinstance(item, dict):
                append(_slot_from_mapping(item, fallback_index=index, default_placeholder=False))

    captions_payload = _read_json_if_exists(plot_captions_path)
    if isinstance(captions_payload, dict):
        values = captions_payload.get("captions") if isinstance(captions_payload.get("captions"), list) else captions_payload.get("figures")
        for index, item in enumerate(values or [], start=1):
            if isinstance(item, dict):
                append(_slot_from_mapping(item, fallback_index=index, default_placeholder=True))
        if values is None:
            for index, (identifier, caption) in enumerate(captions_payload.items(), start=1):
                if isinstance(identifier, str) and isinstance(caption, str):
                    append(
                        FigureSlot(
                            slot_id=identifier,
                            purpose=caption,
                            placeholder=True,
                        )
                    )

    return slots


def _session_paths(cwd: str | Path | None) -> tuple[str | None, str | None, str | None, str | None] | None:
    try:
        state = load_session(cwd)
    except FileNotFoundError:
        return None
    return (
        state.inputs.figures_dir,
        state.artifacts.plot_assets_json,
        state.artifacts.plot_manifest_json,
        state.artifacts.plot_captions_json,
    )


def build_figure_gate_report(
    cwd: str | Path | None = None,
    *,
    figures_dir: str | Path | None = None,
    plot_assets_path: str | Path | None = None,
    plot_manifest_path: str | Path | None = None,
    plot_captions_path: str | Path | None = None,
) -> dict[str, Any]:
    session_paths = _session_paths(cwd)
    if session_paths is not None:
        session_figures_dir, session_plot_assets_path, session_plot_manifest_path, session_plot_captions_path = session_paths
        figures_dir = figures_dir or session_figures_dir
        plot_assets_path = plot_assets_path or session_plot_assets_path
        plot_manifest_path = plot_manifest_path or session_plot_manifest_path
        plot_captions_path = plot_captions_path or session_plot_captions_path

    if not any([plot_assets_path, plot_manifest_path, plot_captions_path]):
        raise ValueError(
            "figure slot sources missing: provide --plot-assets/--plot-manifest/--plot-captions or run inside an initialized session"
        )

    slots = derive_figure_slots(
        plot_assets_path=plot_assets_path,
        plot_manifest_path=plot_manifest_path,
        plot_captions_path=plot_captions_path,
    )
    if not slots:
        report = FigureGateReport(status="pass", decisions=[], blocking_reasons=[])
        payload = report.to_public_dict()
        payload["inventory"] = FigureInventory().to_public_dict()
        return payload

    inventory = inventory_figure_assets(figures_dir) if figures_dir else FigureInventory()
    policy = FigureGatePolicy()
    decisions = [policy.match_slot(slot, inventory.assets) for slot in slots]
    blocking_reasons: list[str] = []
    for decision in decisions:
        if decision.status == "missing":
            blocking_reasons.extend(["figure_asset_missing", "placeholder_figure_unresolved"])
        elif decision.status == "ambiguous":
            blocking_reasons.extend(["ambiguous_figure_match", "placeholder_figure_unresolved"])
        elif decision.status == "human_finalization_needed":
            blocking_reasons.append("placeholder_figure_unresolved")
    status = "pass" if not blocking_reasons else "blocked"
    report = FigureGateReport(status=status, decisions=decisions, blocking_reasons=list(dict.fromkeys(blocking_reasons)))
    payload = report.to_public_dict()
    payload["inventory"] = inventory.to_public_dict()
    payload["slot_count"] = len(slots)
    return payload


def write_figure_gate_report(
    cwd: str | Path | None = None,
    *,
    output_path: str | Path | None = None,
    figures_dir: str | Path | None = None,
    plot_assets_path: str | Path | None = None,
    plot_manifest_path: str | Path | None = None,
    plot_captions_path: str | Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    payload = build_figure_gate_report(
        cwd,
        figures_dir=figures_dir,
        plot_assets_path=plot_assets_path,
        plot_manifest_path=plot_manifest_path,
        plot_captions_path=plot_captions_path,
    )
    path = Path(output_path).resolve() if output_path else figure_gate_report_path(cwd)
    write_json(path, payload)
    return path, payload
