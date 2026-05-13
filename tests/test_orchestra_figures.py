from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from paperorchestra.cli import main as cli_main
from paperorchestra.models import InputBundle
from paperorchestra.orchestra_figures import (
    FIGURE_GATE_SCHEMA_VERSION,
    FigureAsset,
    FigureGatePolicy,
    FigureSlot,
    build_figure_gate_report,
    figure_gate_report_path,
    inventory_figure_assets,
    write_figure_gate_report,
)
from paperorchestra.orchestra_state import OrchestraFacets, OrchestraState
from paperorchestra.session import artifact_path, create_session, load_session, save_session


@contextlib.contextmanager
def _chdir(path: Path):
    old = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def _write_plot_sources(root: Path, *, figure_id: str = "fig_architecture", caption: str = "Architecture overview") -> tuple[Path, Path]:
    plot_assets = root / "plot-assets.json"
    plot_manifest = root / "plot-manifest.json"
    plot_assets.write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "figure_id": figure_id,
                        "caption": caption,
                        "filename": f"{figure_id}.svg",
                        "asset_kind": "generated_placeholder",
                        "review_status": "human_final_artwork_required",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    plot_manifest.write_text(
        json.dumps({"figures": [{"figure_id": figure_id, "caption": caption, "purpose": caption}]}),
        encoding="utf-8",
    )
    return plot_assets, plot_manifest


def _init_session(root: Path, *, figures_dir: Path, plot_assets: Path, plot_manifest: Path):
    for name, content in {
        "idea.md": "Synthetic idea.\n",
        "experimental_log.md": "Synthetic log.\n",
        "template.tex": "\\documentclass{article}\\begin{document}\\end{document}\n",
        "guidelines.md": "Synthetic guidelines.\n",
    }.items():
        (root / name).write_text(content, encoding="utf-8")
    state = create_session(
        root,
        InputBundle(
            str(root / "idea.md"),
            str(root / "experimental_log.md"),
            str(root / "template.tex"),
            str(root / "guidelines.md"),
            str(figures_dir),
        ),
    )
    paper = artifact_path(root, "paper.full.tex")
    paper.write_text("Synthetic draft with placeholder figure.\n", encoding="utf-8")
    state.artifacts.paper_full_tex = str(paper)
    state.artifacts.plot_assets_json = str(plot_assets)
    state.artifacts.plot_manifest_json = str(plot_manifest)
    state.facets = getattr(state, "facets", None)
    save_session(root, state)
    return load_session(root)


class OrchestraFigureGateTests(unittest.TestCase):
    def test_figure_inventory_records_supplied_generic_assets_with_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            asset = Path(tmp) / "supplied_architecture_diagram.pdf"
            asset.write_bytes(b"synthetic figure bytes")
            inventory = inventory_figure_assets(tmp)

        self.assertEqual(len(inventory.assets), 1)
        self.assertEqual(inventory.assets[0].filename, "supplied_architecture_diagram.pdf")
        self.assertEqual(len(inventory.assets[0].sha256), 64)

    def test_figure_inventory_public_output_redacts_raw_private_filename_and_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            asset = Path(tmp) / "PRIVATE_SECRET_architecture_diagram.pdf"
            asset.write_bytes(b"synthetic figure bytes")
            inventory = inventory_figure_assets(tmp)
            rendered = json.dumps(inventory.to_public_dict(), ensure_ascii=False)

        self.assertIn("redacted-figure-asset:", rendered)
        self.assertIn("sha256", rendered)
        self.assertNotIn("PRIVATE_SECRET", rendered)
        self.assertNotIn(str(asset), rendered)
        self.assertNotIn(asset.name, rendered)

    def test_safe_figure_slot_semantic_match_marks_slot_matched(self) -> None:
        decision = FigureGatePolicy().match_slot(
            FigureSlot(slot_id="F1", purpose="architecture diagram", placeholder=True),
            [FigureAsset(path="/tmp/supplied_architecture_diagram.pdf", filename="supplied_architecture_diagram.pdf", sha256="a" * 64)],
        )
        self.assertEqual(decision.status, "matched")
        self.assertEqual(decision.asset_filename, "supplied_architecture_diagram.pdf")

    def test_ambiguous_figure_match_records_human_finalization_blocker(self) -> None:
        decision = FigureGatePolicy().match_slot(
            FigureSlot(slot_id="F1", purpose="architecture diagram", placeholder=True),
            [FigureAsset(path="/tmp/unrelated_plot.pdf", filename="unrelated_plot.pdf", sha256="a" * 64)],
        )
        self.assertEqual(decision.status, "missing")
        self.assertIn("figure_asset_missing", decision.reasons)

    def test_placeholder_only_figure_state_blocks_final_readiness(self) -> None:
        state = OrchestraState.new(
            cwd="/tmp/example",
            facets=OrchestraFacets(figures="placeholder_only", quality="human_finalization_candidate"),
        )
        updated = FigureGatePolicy().apply_to_state(state)

        self.assertNotEqual(updated.readiness.label, "ready_for_human_finalization")
        self.assertIn("placeholder_figure_unresolved", updated.blocking_reasons)

    def test_figure_gate_report_matches_one_supplied_asset_without_applying_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            figures = root / "figures"
            figures.mkdir()
            (figures / "architecture_overview.pdf").write_bytes(b"synthetic figure bytes")
            plot_assets, plot_manifest = _write_plot_sources(root, caption="Architecture overview")

            report = build_figure_gate_report(
                root,
                figures_dir=figures,
                plot_assets_path=plot_assets,
                plot_manifest_path=plot_manifest,
            )

        self.assertEqual(report["schema_version"], FIGURE_GATE_SCHEMA_VERSION)
        self.assertEqual(report["status"], "pass")
        decision = report["decisions"][0]
        self.assertEqual(decision["status"], "matched")
        self.assertTrue(decision["replacement_proposed"])
        self.assertFalse(decision["replacement_applied"])
        self.assertTrue(decision["private_safe"])
        self.assertTrue(report["private_safe_summary"])
        self.assertEqual(report["acceptance_gate_impacts"]["supplied_figures_inventoried_matched_or_blocked"], "pass")

    def test_figure_gate_report_marks_multiple_plausible_assets_ambiguous_without_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            figures = root / "figures"
            figures.mkdir()
            (figures / "architecture_overview_left.pdf").write_bytes(b"left")
            (figures / "architecture_overview_right.pdf").write_bytes(b"right")
            plot_assets, plot_manifest = _write_plot_sources(root, caption="Architecture overview")

            report = build_figure_gate_report(
                root,
                figures_dir=figures,
                plot_assets_path=plot_assets,
                plot_manifest_path=plot_manifest,
            )

        self.assertEqual(report["status"], "blocked")
        decision = report["decisions"][0]
        self.assertEqual(decision["status"], "ambiguous")
        self.assertFalse(decision["replacement_proposed"])
        self.assertIn("multiple_plausible_figure_matches", decision["reasons"])

    def test_figure_gate_report_marks_missing_asset_for_placeholder_slot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            figures = root / "figures"
            figures.mkdir()
            (figures / "unrelated_plot.pdf").write_bytes(b"unrelated")
            plot_assets, plot_manifest = _write_plot_sources(root, caption="Architecture overview")

            report = build_figure_gate_report(
                root,
                figures_dir=figures,
                plot_assets_path=plot_assets,
                plot_manifest_path=plot_manifest,
            )

        self.assertEqual(report["status"], "blocked")
        decision = report["decisions"][0]
        self.assertEqual(decision["status"], "missing")
        self.assertFalse(decision["replacement_proposed"])
        self.assertIn("figure_asset_missing", decision["reasons"])
        self.assertIn("placeholder_figure_unresolved", report["blocking_reasons"])

    def test_figure_gate_public_report_redacts_private_slot_filename_and_caption(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            figures = root / "figures"
            figures.mkdir()
            private_name = "PRIVATE_SECRET_architecture.pdf"
            private_caption = "PRIVATE_CAPTION_SHOULD_NOT_LEAK architecture overview"
            (figures / private_name).write_bytes(b"private")
            plot_assets, plot_manifest = _write_plot_sources(
                root,
                figure_id="PRIVATE_SLOT_SHOULD_NOT_LEAK",
                caption=private_caption,
            )

            report = build_figure_gate_report(
                root,
                figures_dir=figures,
                plot_assets_path=plot_assets,
                plot_manifest_path=plot_manifest,
            )
            rendered = json.dumps(report, ensure_ascii=False)

        self.assertIn("redacted-figure-slot:", rendered)
        self.assertNotIn("PRIVATE_SECRET", rendered)
        self.assertNotIn("PRIVATE_SLOT_SHOULD_NOT_LEAK", rendered)
        self.assertNotIn("PRIVATE_CAPTION_SHOULD_NOT_LEAK", rendered)
        self.assertNotIn(str(figures), rendered)

    def test_audit_figure_gate_cli_writes_explicit_non_session_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            figures = root / "figures"
            figures.mkdir()
            (figures / "architecture_overview.pdf").write_bytes(b"synthetic")
            plot_assets, plot_manifest = _write_plot_sources(root, caption="Architecture overview")
            output = root / "figure-gate.json"
            stdout = io.StringIO()
            with _chdir(root), contextlib.redirect_stdout(stdout):
                exit_code = cli_main(
                    [
                        "audit-figure-gate",
                        "--figures-dir",
                        str(figures),
                        "--plot-assets",
                        str(plot_assets),
                        "--plot-manifest",
                        str(plot_manifest),
                        "--output",
                        str(output),
                    ]
                )
            payload = json.loads(stdout.getvalue())
            output_exists = output.exists()

        self.assertEqual(exit_code, 0)
        self.assertTrue(output_exists)
        self.assertEqual(payload["report"]["schema_version"], FIGURE_GATE_SCHEMA_VERSION)

    def test_audit_figure_gate_cli_merges_explicit_figures_dir_with_session_plot_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session_figures = root / "session-figures"
            session_figures.mkdir()
            override_figures = root / "override-figures"
            override_figures.mkdir()
            (override_figures / "architecture_overview.pdf").write_bytes(b"synthetic")
            plot_assets, plot_manifest = _write_plot_sources(root, caption="Architecture overview")
            _init_session(root, figures_dir=session_figures, plot_assets=plot_assets, plot_manifest=plot_manifest)
            stdout = io.StringIO()
            with _chdir(root), contextlib.redirect_stdout(stdout):
                exit_code = cli_main(["audit-figure-gate", "--figures-dir", str(override_figures)])
            payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["report"]["status"], "pass")
        self.assertEqual(payload["report"]["decisions"][0]["status"], "matched")

    def test_audit_figure_gate_cli_merges_explicit_plot_sources_with_session_figures_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session_figures = root / "session-figures"
            session_figures.mkdir()
            (session_figures / "architecture_overview.pdf").write_bytes(b"synthetic")
            session_assets, session_manifest = _write_plot_sources(root, caption="Unmatched session source")
            _init_session(root, figures_dir=session_figures, plot_assets=session_assets, plot_manifest=session_manifest)
            explicit_root = root / "explicit"
            explicit_root.mkdir()
            explicit_assets, explicit_manifest = _write_plot_sources(explicit_root, caption="Architecture overview")
            stdout = io.StringIO()
            with _chdir(root), contextlib.redirect_stdout(stdout):
                exit_code = cli_main(
                    [
                        "audit-figure-gate",
                        "--plot-assets",
                        str(explicit_assets),
                        "--plot-manifest",
                        str(explicit_manifest),
                    ]
                )
            payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["report"]["status"], "pass")
        self.assertEqual(payload["report"]["decisions"][0]["status"], "matched")

    def test_audit_figure_gate_cli_without_session_or_slot_sources_fails_actionably(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            figures = root / "figures"
            figures.mkdir()
            stderr = io.StringIO()
            with _chdir(root), contextlib.redirect_stderr(stderr):
                exit_code = cli_main(["audit-figure-gate", "--figures-dir", str(figures)])
            message = stderr.getvalue()

        self.assertEqual(exit_code, 1)
        self.assertIn("figure slot sources missing", message)
        self.assertIn("--plot-assets", message)

    def test_figure_gate_derives_slots_from_pipeline_caption_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            figures = root / "figures"
            figures.mkdir()
            (figures / "architecture_overview.pdf").write_bytes(b"synthetic")
            captions = root / "plot_captions.json"
            captions.write_text(json.dumps({"fig_architecture": "Architecture overview"}), encoding="utf-8")

            report = build_figure_gate_report(root, figures_dir=figures, plot_captions_path=captions)

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["slot_count"], 1)
        self.assertEqual(report["decisions"][0]["status"], "matched")

    def test_figure_gate_manifest_non_placeholder_entries_do_not_false_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            figures = root / "figures"
            figures.mkdir()
            manifest = root / "plot-manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "figures": [
                            {
                                "figure_id": "fig_architecture",
                                "caption": "Architecture overview",
                                "placeholder": False,
                                "asset_kind": "final_artwork",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            report = build_figure_gate_report(root, figures_dir=figures, plot_manifest_path=manifest)

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["decisions"][0]["status"], "already_realized")
        self.assertNotIn("placeholder_figure_unresolved", report["blocking_reasons"])

    def test_figure_gate_write_uses_session_artifact_path_and_does_not_mutate_paper(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            figures = root / "figures"
            figures.mkdir()
            (figures / "architecture_overview.pdf").write_bytes(b"synthetic")
            plot_assets, plot_manifest = _write_plot_sources(root, caption="Architecture overview")
            state = _init_session(root, figures_dir=figures, plot_assets=plot_assets, plot_manifest=plot_manifest)
            paper = Path(state.artifacts.paper_full_tex)
            before = paper.read_text(encoding="utf-8")

            path, report = write_figure_gate_report(root)
            expected_path = figure_gate_report_path(root)
            after = paper.read_text(encoding="utf-8")
            output_exists = path.exists()

        self.assertEqual(path, expected_path)
        self.assertTrue(output_exists)
        self.assertEqual(before, after)
        self.assertFalse(report["decisions"][0]["replacement_applied"])
