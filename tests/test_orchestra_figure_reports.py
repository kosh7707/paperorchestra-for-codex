from __future__ import annotations

import json
from pathlib import Path

from paperorchestra.core.models import ArtifactIndex, InputBundle, SessionState, utc_now_iso
from paperorchestra.core.session import save_session, set_current_session
from paperorchestra.orchestra import figure_reports, figures


def test_figures_facade_preserves_public_report_entrypoints() -> None:
    assert figures.figure_gate_report_path is figure_reports.figure_gate_report_path
    assert figures.derive_figure_slots is figure_reports.derive_figure_slots
    assert figures.build_figure_gate_report is not figure_reports.build_figure_gate_report
    assert figures.write_figure_gate_report is not figure_reports.write_figure_gate_report


def test_derive_figure_slots_deduplicates_sources_by_slot_id(tmp_path: Path) -> None:
    assets = tmp_path / "plot-assets.json"
    assets.write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "figure_id": "pipeline",
                        "purpose": "Pipeline overview",
                        "asset_kind": "generated_placeholder",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "plot-manifest.json"
    manifest.write_text(
        json.dumps({"figures": [{"figure_id": "pipeline", "purpose": "Duplicate manifest"}, {"id": "cost", "caption": "Cost"}]}),
        encoding="utf-8",
    )

    slots = figure_reports.derive_figure_slots(plot_assets_path=assets, plot_manifest_path=manifest)

    assert [(slot.slot_id, slot.purpose, slot.placeholder) for slot in slots] == [
        ("pipeline", "Pipeline overview", True),
        ("cost", "Cost", False),
    ]


def test_build_figure_gate_report_matches_real_asset(tmp_path: Path) -> None:
    figures_dir = tmp_path / "figures"
    figures_dir.mkdir()
    (figures_dir / "method-data-flow.pdf").write_text("pdf", encoding="utf-8")
    captions = tmp_path / "captions.json"
    captions.write_text(json.dumps({"figures": [{"id": "flow", "caption": "Method data flow"}]}), encoding="utf-8")

    report = figure_reports.build_figure_gate_report(figures_dir=figures_dir, plot_captions_path=captions)

    assert report["status"] == "pass"
    assert report["summary"]["matched"] == 1
    assert report["inventory"]["asset_count"] == 1


def test_figures_facade_report_uses_facade_policy(monkeypatch, tmp_path: Path) -> None:
    figures_dir = tmp_path / "figures"
    figures_dir.mkdir()
    (figures_dir / "method-data-flow.pdf").write_text("pdf", encoding="utf-8")
    captions = tmp_path / "captions.json"
    captions.write_text(json.dumps({"figures": [{"id": "flow", "caption": "Method data flow"}]}), encoding="utf-8")

    class FacadePolicy:
        def match_slot(self, slot, assets, generated_assets=None):
            return figures.FigureMatchDecision(slot_id=slot.slot_id, status="missing", reasons=["facade_policy_used"])

    monkeypatch.setattr(figures, "FigureGatePolicy", FacadePolicy)

    facade_report = figures.build_figure_gate_report(figures_dir=figures_dir, plot_captions_path=captions)
    direct_report = figure_reports.build_figure_gate_report(figures_dir=figures_dir, plot_captions_path=captions)

    assert facade_report["status"] == "blocked"
    assert facade_report["decisions"][0]["reasons"] == ["facade_policy_used"]
    assert direct_report["status"] == "pass"
    assert direct_report["summary"]["matched"] == 1

    output = tmp_path / "facade-write.json"
    _path, facade_write_payload = figures.write_figure_gate_report(
        output_path=output,
        figures_dir=figures_dir,
        plot_captions_path=captions,
    )

    assert facade_write_payload["status"] == "blocked"
    assert facade_write_payload["decisions"][0]["reasons"] == ["facade_policy_used"]
    assert json.loads(output.read_text(encoding="utf-8")) == facade_write_payload


def test_build_figure_gate_report_uses_generated_placeholder_asset(tmp_path: Path) -> None:
    generated = tmp_path / "generated"
    generated.mkdir()
    snippet = generated / "pipeline.tex"
    snippet.write_text("% generated placeholder", encoding="utf-8")
    assets = tmp_path / "plot-assets.json"
    assets.write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "figure_id": "pipeline",
                        "purpose": "Pipeline overview",
                        "asset_kind": "generated_placeholder",
                        "latex_snippet_path": "generated/pipeline.tex",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    report = figure_reports.build_figure_gate_report(cwd=tmp_path, plot_assets_path=assets)

    assert report["status"] == "pass"
    assert report["summary"]["generated_asset_available"] == 1
    assert report["decisions"][0]["status"] == "generated_asset_available"


def test_build_figure_gate_report_blocks_missing_and_ambiguous_assets(tmp_path: Path) -> None:
    missing_captions = tmp_path / "missing-captions.json"
    missing_captions.write_text(json.dumps({"figures": [{"id": "flow", "caption": "Method data flow"}]}), encoding="utf-8")

    missing_report = figure_reports.build_figure_gate_report(plot_captions_path=missing_captions)

    assert missing_report["status"] == "blocked"
    assert missing_report["blocking_reasons"] == ["figure_asset_missing", "placeholder_figure_unresolved"]

    figures_dir = tmp_path / "figures"
    figures_dir.mkdir()
    (figures_dir / "method-flow-alpha.pdf").write_text("pdf", encoding="utf-8")
    (figures_dir / "method-flow-beta.pdf").write_text("pdf", encoding="utf-8")
    ambiguous_captions = tmp_path / "ambiguous-captions.json"
    ambiguous_captions.write_text(json.dumps({"figures": [{"id": "flow", "caption": "Method flow"}]}), encoding="utf-8")

    ambiguous_report = figure_reports.build_figure_gate_report(figures_dir=figures_dir, plot_captions_path=ambiguous_captions)

    assert ambiguous_report["status"] == "blocked"
    assert ambiguous_report["summary"]["ambiguous"] == 1
    assert ambiguous_report["blocking_reasons"] == ["ambiguous_figure_match", "placeholder_figure_unresolved"]


def test_write_figure_gate_report_writes_payload(tmp_path: Path) -> None:
    captions = tmp_path / "captions.json"
    captions.write_text(json.dumps({"figures": []}), encoding="utf-8")
    output = tmp_path / "figure-gate.json"

    path, payload = figure_reports.write_figure_gate_report(output_path=output, plot_captions_path=captions)

    assert path == output.resolve()
    assert json.loads(output.read_text(encoding="utf-8")) == payload
    assert payload["status"] == "pass"


def test_build_figure_gate_report_uses_session_paths(tmp_path: Path) -> None:
    figures_dir = tmp_path / "figures"
    figures_dir.mkdir()
    (figures_dir / "method-data-flow.pdf").write_text("pdf", encoding="utf-8")
    captions = tmp_path / "captions.json"
    captions.write_text(json.dumps({"figures": [{"id": "flow", "caption": "Method data flow"}]}), encoding="utf-8")
    now = utc_now_iso()
    state = SessionState(
        session_id="figure-report-test",
        created_at=now,
        updated_at=now,
        current_phase="test",
        active_artifact=None,
        inputs=InputBundle(
            idea_path="idea.md",
            experimental_log_path="exp.md",
            template_path="template.tex",
            guidelines_path="guidelines.md",
            figures_dir=str(figures_dir),
        ),
        artifacts=ArtifactIndex(plot_captions_json=str(captions)),
    )
    save_session(tmp_path, state)
    set_current_session(tmp_path, state.session_id)

    report = figure_reports.build_figure_gate_report(cwd=tmp_path)

    assert report["status"] == "pass"
    assert report["summary"]["matched"] == 1
