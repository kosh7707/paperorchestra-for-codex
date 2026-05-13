from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from .orchestra_policies import ReadinessPolicy
from .orchestra_state import OrchestraState

FIGURE_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".svg"}


@dataclass(frozen=True)
class FigureAsset:
    path: str
    filename: str
    sha256: str


@dataclass(frozen=True)
class FigureInventory:
    assets: list[FigureAsset] = field(default_factory=list)


@dataclass(frozen=True)
class FigureSlot:
    slot_id: str
    purpose: str
    placeholder: bool = True


@dataclass(frozen=True)
class FigureMatchDecision:
    slot_id: str
    status: str
    asset_filename: str | None = None
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FigureGateReport:
    status: str
    decisions: list[FigureMatchDecision]
    blocking_reasons: list[str] = field(default_factory=list)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        for asset in assets:
            filename_tokens = self._tokens(Path(asset.filename).stem.replace("_", " ").replace("-", " "))
            if purpose_tokens and purpose_tokens.issubset(filename_tokens):
                return FigureMatchDecision(slot_id=slot.slot_id, status="matched", asset_filename=asset.filename)
        return FigureMatchDecision(
            slot_id=slot.slot_id,
            status="human_finalization_needed",
            reasons=["ambiguous_or_missing_figure_match"],
        )

    def apply_to_state(self, state: OrchestraState) -> OrchestraState:
        updated = state.clone()
        if updated.facets.figures == "placeholder_only" and "placeholder_figure_unresolved" not in updated.blocking_reasons:
            updated.blocking_reasons.append("placeholder_figure_unresolved")
        return ReadinessPolicy().apply(updated)

    def _tokens(self, text: str) -> set[str]:
        return {token for token in text.lower().replace(".", " ").split() if len(token) > 2 and token not in {"the", "and"}}
