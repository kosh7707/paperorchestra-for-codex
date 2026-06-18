from __future__ import annotations

import hashlib
import re
from pathlib import Path

from paperorchestra.orchestra.figure_records import (
    FIGURE_EXTENSIONS,
    FigureAsset,
    FigureInventory,
    FigureMatchDecision,
    FigureSlot,
    GeneratedFigureAvailability,
)

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
    def match_slot(
        self,
        slot: FigureSlot,
        assets: list[FigureAsset],
        generated_assets: dict[str, GeneratedFigureAvailability] | None = None,
    ) -> FigureMatchDecision:
        purpose_tokens = self._tokens(slot.purpose)
        if not slot.placeholder:
            return FigureMatchDecision(slot_id=slot.slot_id, status="already_realized", reasons=["slot_is_not_placeholder"])
        generated_asset = (generated_assets or {}).get(slot.slot_id)
        generated_decision = (
            FigureMatchDecision(
                slot_id=slot.slot_id,
                status="generated_asset_available",
                reasons=list(generated_asset.reasons),
                selected_asset_sha256=generated_asset.sha256,
                replacement_proposed=False,
                replacement_applied=False,
            )
            if generated_asset is not None
            else None
        )
        if not purpose_tokens:
            if generated_decision is not None:
                return generated_decision
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
            if generated_decision is not None:
                return generated_decision
            return FigureMatchDecision(
                slot_id=slot.slot_id,
                status="missing",
                reasons=["figure_asset_missing"],
            )
        threshold = min(2, len(purpose_tokens))
        best_score = max(score for score, _asset in scored)
        candidates = [asset for score, asset in scored if score == best_score and score >= threshold]
        if not candidates:
            if generated_decision is not None:
                return generated_decision
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

    def _tokens(self, text: str) -> set[str]:
        normalized = re.sub(r"[^a-zA-Z0-9]+", " ", text.lower())
        return {token for token in normalized.split() if len(token) > 2 and token not in _STOPWORDS}
