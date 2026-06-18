from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.loop_engine.quality.action_core import _action
from paperorchestra.loop_engine.quality.utils import _read_json_if_exists


def _generated_placeholder_figure_actions(state: Any) -> list[dict[str, Any]]:
    payload = _read_json_if_exists(state.artifacts.plot_assets_json)
    paper_path = Path(state.artifacts.paper_full_tex) if state.artifacts.paper_full_tex else None
    if not isinstance(payload, dict) or not paper_path or not paper_path.exists():
        return []
    latex = paper_path.read_text(encoding="utf-8", errors="replace")
    if not _used_placeholder_assets(payload, latex):
        return []
    return [_placeholder_action(state)]


def _used_placeholder_assets(payload: dict[str, Any], latex: str) -> list[str]:
    return [
        str(asset.get("figure_id") or asset.get("filename") or "generated_placeholder")
        for asset in payload.get("assets") or []
        if isinstance(asset, dict) and _placeholder_asset_is_used(asset, latex)
    ]


def _placeholder_asset_is_used(asset: dict[str, Any], latex: str) -> bool:
    if asset.get("asset_kind") != "generated_placeholder" and asset.get("review_status") != "human_final_artwork_required":
        return False
    references = [asset.get("latex_snippet_path"), asset.get("latex_path"), asset.get("filename")]
    return any(isinstance(ref, str) and ref and ref in latex for ref in references)


def _placeholder_action(state: Any) -> dict[str, Any]:
    return _action(
        action_id="figure:final-artwork",
        code="final_figure_assets_non_reviewable",
        source=state.artifacts.plot_assets_json,
        target="final figures",
        automation="human_needed",
        reason="Generated placeholder figure assets are still used in the manuscript, so the artifact is not reviewable until human final artwork replaces or removes them.",
        suggested_commands=[
            "Replace generated placeholder assets with human-authored final figures, or remove/defer those figures.",
            "paperorchestra critique",
            "paperorchestra qa-loop --quality-mode claim_safe",
        ],
        ralph_instruction="Stop automatic paper packaging: placeholder figures are acceptable draft scaffolds but not review-ready evidence.",
        preconditions=["tier_1_structural must remain pass"],
    )
