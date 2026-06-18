from __future__ import annotations

from pathlib import Path

from paperorchestra.orchestra import figure_core, figures
from paperorchestra.orchestra.state import OrchestraFacets, OrchestraState


def test_figures_facade_preserves_public_models_and_policy_adapter() -> None:
    assert figures.FIGURE_EXTENSIONS is figure_core.FIGURE_EXTENSIONS
    assert figures.FIGURE_GATE_SCHEMA_VERSION == figure_core.FIGURE_GATE_SCHEMA_VERSION
    assert figures.FIGURE_GATE_REPORT_FILENAME == figure_core.FIGURE_GATE_REPORT_FILENAME
    assert figures.FigureAsset is figure_core.FigureAsset
    assert figures.FigureInventory is figure_core.FigureInventory
    assert figures.FigureSlot is figure_core.FigureSlot
    assert figures.GeneratedFigureAvailability is figure_core.GeneratedFigureAvailability
    assert figures.FigureMatchDecision is figure_core.FigureMatchDecision
    assert figures.FigureGateReport is figure_core.FigureGateReport
    assert figures.FigureGatePolicy is not figure_core.FigureGatePolicy
    assert issubclass(figures.FigureGatePolicy, figure_core.FigureGatePolicy)
    assert not hasattr(figure_core.FigureGatePolicy, "apply_to_state")
    assert hasattr(figures.FigureGatePolicy, "apply_to_state")
    assert figures.inventory_figure_assets is figure_core.inventory_figure_assets


def test_figure_core_has_no_orchestration_runtime_imports() -> None:
    source = Path(figure_core.__file__).read_text(encoding="utf-8")

    forbidden = [
        "paperorchestra.core.session",
        "paperorchestra.core.io",
        "paperorchestra.orchestra.policies",
        "paperorchestra.orchestra.state",
        "ReadinessPolicy",
        "OrchestraState",
    ]

    for marker in forbidden:
        assert marker not in source


def test_figures_policy_adapter_preserves_state_api(tmp_path: Path) -> None:
    state = OrchestraState.new(cwd=tmp_path, facets=OrchestraFacets(figures="placeholder_only"))

    updated = figures.FigureGatePolicy().apply_to_state(state)

    assert "placeholder_figure_unresolved" in updated.blocking_reasons
    assert "placeholder_figure_unresolved" not in state.blocking_reasons


def test_figure_asset_public_dict_redacts_filename_and_keeps_extension() -> None:
    asset = figure_core.FigureAsset(path="/private/SECRET-figure.pdf", filename="SECRET-figure.pdf", sha256="abc123")

    public = asset.to_public_dict()

    assert public["asset_label"].startswith("redacted-figure-asset:")
    assert "SECRET" not in str(public)
    assert public["sha256"] == "abc123"
    assert public["extension"] == ".pdf"


def test_figure_policy_prefers_generated_placeholder_when_no_real_asset_matches() -> None:
    policy = figure_core.FigureGatePolicy()
    slot = figure_core.FigureSlot(slot_id="pipeline", purpose="Pipeline overview")
    generated = {
        "pipeline": figure_core.GeneratedFigureAvailability(
            figure_id="pipeline",
            sha256="generated-sha",
            reasons=("generated_asset_available", "human_final_artwork_required"),
        )
    }

    decision = policy.match_slot(slot, [], generated)

    assert decision.status == "generated_asset_available"
    assert decision.selected_asset_sha256 == "generated-sha"
    assert decision.replacement_proposed is False
    assert decision.to_public_dict()["slot_id"] == "pipeline"


def test_figure_policy_matches_real_asset_by_purpose_tokens() -> None:
    policy = figure_core.FigureGatePolicy()
    slot = figure_core.FigureSlot(slot_id="method-flow", purpose="Method data flow")
    asset = figure_core.FigureAsset(path="method-data-flow.pdf", filename="method-data-flow.pdf", sha256="real-sha")

    decision = policy.match_slot(slot, [asset])

    assert decision.status == "matched"
    assert decision.asset_filename == "method-data-flow.pdf"
    assert decision.selected_asset_sha256 == "real-sha"
    assert decision.replacement_proposed is True


def test_inventory_figure_assets_filters_supported_extensions(tmp_path: Path) -> None:
    (tmp_path / "a.pdf").write_text("pdf", encoding="utf-8")
    (tmp_path / "b.txt").write_text("txt", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "c.png").write_text("png", encoding="utf-8")

    inventory = figure_core.inventory_figure_assets(tmp_path)

    assert [asset.filename for asset in inventory.assets] == ["a.pdf", "c.png"]
    assert inventory.to_public_dict()["asset_count"] == 2
