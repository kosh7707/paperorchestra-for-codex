from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from paperorchestra.citation_integrity import rendered_reference_audit_path, write_rendered_reference_audit
from paperorchestra.cli import main as cli_main
from paperorchestra.models import InputBundle
from paperorchestra.narrative import write_planning_artifacts
from paperorchestra.orchestra_citation_quality import (
    CITATION_QUALITY_GATE_SCHEMA_VERSION,
    build_citation_quality_gate,
    citation_quality_gate_path,
)
from paperorchestra.orchestrator import run_until_blocked
from paperorchestra.quality_loop import build_quality_eval
from paperorchestra.quality_loop_plan_logic import _quality_eval_actions
from paperorchestra.session import artifact_path, create_session, load_session, save_session


@contextlib.contextmanager
def _chdir(path: Path):
    old = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def _init_session(root: Path, *, cite_key: str = "Known", title: str = "Known Title", paper_text: str | None = None):
    for name, content in {
        "idea.md": "Synthetic idea for citation quality testing.\n",
        "experimental_log.md": "Synthetic experiment log.\n",
        "template.tex": "\\documentclass{article}\n\\begin{document}\\end{document}\n",
        "guidelines.md": "Synthetic guidelines.\n",
    }.items():
        (root / name).write_text(content, encoding="utf-8")
    (root / "figures").mkdir()
    state = create_session(
        root,
        InputBundle(
            str(root / "idea.md"),
            str(root / "experimental_log.md"),
            str(root / "template.tex"),
            str(root / "guidelines.md"),
            str(root / "figures"),
        ),
    )
    paper = artifact_path(root, "paper.full.tex")
    paper.write_text(paper_text or f"Synthetic claim~\\cite{{{cite_key}}}.\n", encoding="utf-8")
    refs = artifact_path(root, "references.bib")
    refs.write_text(
        f"""
        @article{{{cite_key},
          title = {{{title}}},
          author = {{Ada Example}},
          year = {{2026}}
        }}
        """,
        encoding="utf-8",
    )
    registry = artifact_path(root, "citation_registry.json")
    registry.write_text(
        json.dumps(
            [
                {
                    "paper_id": f"synthetic-{cite_key}",
                    "title": title,
                    "year": 2026,
                    "abstract": "Synthetic abstract.",
                    "authors": ["Ada Example"],
                    "citation_count": 1,
                    "bibtex_key": cite_key,
                }
            ]
        ),
        encoding="utf-8",
    )
    citation_map = artifact_path(root, "citation_map.json")
    citation_map.write_text(
        json.dumps({cite_key: {"title": title, "authors": ["Ada Example"], "year": 2026, "paper_id": f"synthetic-{cite_key}"}}),
        encoding="utf-8",
    )
    bbl = artifact_path(root, "paper.full.bbl")
    bbl.write_text(f"\\bibitem{{{cite_key}}} Rendered {cite_key}.\n", encoding="utf-8")
    state.artifacts.paper_full_tex = str(paper)
    state.artifacts.references_bib = str(refs)
    state.artifacts.citation_registry_json = str(registry)
    state.artifacts.citation_map_json = str(citation_map)
    save_session(root, state)
    write_rendered_reference_audit(root, quality_mode="claim_safe")
    return load_session(root)


def _write_claim_map(root: Path, claims: list[dict]) -> Path:
    path = artifact_path(root, "claim_map.json")
    path.write_text(json.dumps({"claims": claims}), encoding="utf-8")
    state = load_session(root)
    state.artifacts.claim_map_json = str(path)
    save_session(root, state)
    return path


def _write_support_review(root: Path, items: list[dict]) -> Path:
    state = load_session(root)
    path = Path(state.artifacts.paper_full_tex).resolve().parent / "citation_support_review.json"
    path.write_text(json.dumps({"items": items, "evidence_mode": "web"}), encoding="utf-8")
    return path


class CitationQualityGateTests(unittest.TestCase):
    def test_claim_safe_unknown_metadata_for_critical_claim_is_hard_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root, cite_key="UnknownMeta", title="Unknown")
            _write_claim_map(
                root,
                [
                    {
                        "id": "C1",
                        "claim_type": "numeric",
                        "graph_role": "root",
                        "required": True,
                        "citation_required": True,
                        "citation_keys": ["UnknownMeta"],
                    }
                ],
            )

            report = build_citation_quality_gate(root, quality_mode="claim_safe")
            rendered = json.dumps(report, ensure_ascii=False)

        self.assertEqual(report["schema_version"], CITATION_QUALITY_GATE_SCHEMA_VERSION)
        self.assertEqual(report["status"], "fail")
        self.assertIn("critical_unknown_reference", report["hard_gate_failures"])
        self.assertEqual(report["acceptance_gate_impacts"]["no_unknown_refs_for_critical_claims"], "fail")
        self.assertNotIn("UnknownMeta", rendered)
        self.assertNotIn("Unknown", rendered)
        self.assertNotIn(tmp, rendered)

    def test_same_unknown_metadata_is_warning_when_explicitly_noncritical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root, cite_key="UnknownMeta", title="Unknown")
            _write_claim_map(
                root,
                [
                    {
                        "id": "BG1",
                        "claim_type": "background",
                        "graph_role": "background",
                        "required": False,
                        "citation_required": False,
                        "citation_keys": ["UnknownMeta"],
                    }
                ],
            )

            report = build_citation_quality_gate(root, quality_mode="claim_safe")

        self.assertEqual(report["status"], "warn")
        self.assertNotIn("critical_unknown_reference", report["hard_gate_failures"])
        self.assertIn("noncritical_unknown_reference", report["warning_codes"])

    def test_unsupported_or_metadata_only_support_for_critical_claim_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root, cite_key="Known", title="Known Title")
            _write_support_review(
                root,
                [
                    {
                        "id": "support-1",
                        "sentence": "PRIVATE_RAW_SENTENCE_SHOULD_NOT_LEAK~\\cite{Known}.",
                        "citation_keys": ["Known"],
                        "support_status": "metadata_only",
                        "critical": True,
                    }
                ],
            )

            report = build_citation_quality_gate(root, quality_mode="claim_safe")
            rendered = json.dumps(report, ensure_ascii=False)

        self.assertEqual(report["status"], "fail")
        self.assertIn("critical_unsupported_citation", report["hard_gate_failures"])
        self.assertNotIn("PRIVATE_RAW_SENTENCE_SHOULD_NOT_LEAK", rendered)
        self.assertNotIn("Known Title", rendered)
        self.assertNotIn(tmp, rendered)

    def test_supported_critical_citation_with_known_metadata_passes_hard_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root, cite_key="Known", title="Known Title")
            _write_support_review(
                root,
                [
                    {
                        "id": "support-1",
                        "sentence": "Synthetic supported sentence~\\cite{Known}.",
                        "citation_keys": ["Known"],
                        "support_status": "supported",
                        "critical": True,
                    }
                ],
            )

            report = build_citation_quality_gate(root, quality_mode="claim_safe")

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["hard_gate_failures"], [])
        self.assertEqual(report["counts"]["critical_unsupported_count"], 0)

    def test_claim_safe_missing_rendered_metadata_for_critical_citation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root, cite_key="Known", title="Known Title")
            rendered_reference_audit_path(root).unlink()
            _write_support_review(
                root,
                [
                    {
                        "id": "support-1",
                        "sentence": "Synthetic supported sentence~\\cite{Known}.",
                        "citation_keys": ["Known"],
                        "support_status": "supported",
                        "critical": True,
                    }
                ],
            )

            report = build_citation_quality_gate(root, quality_mode="claim_safe")

        self.assertEqual(report["status"], "fail")
        self.assertIn("critical_citation_metadata_missing", report["hard_gate_failures"])

    def test_noncritical_duplicate_warning_does_not_mask_critical_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root, cite_key="UnknownMeta", title="Unknown")
            _write_claim_map(root, [{"id": "C1", "claim_type": "numeric", "required": True, "citation_keys": ["UnknownMeta"]}])
            integrity = artifact_path(root, "citation_integrity.audit.json")
            integrity.write_text(
                json.dumps(
                    {
                        "schema_version": "citation-integrity-audit/1",
                        "status": "fail",
                        "manuscript_sha256": "stale-is-tested-elsewhere",
                        "failing_codes": ["citation_duplicate_support", "citation_bomb_detected"],
                        "checks": {
                            "duplicate_support": {"duplicate_keys": ["Repeated"]},
                            "citation_density": {"bomb_sentences": [{"citation_keys": ["A", "B", "C", "D"]}]},
                        },
                    }
                ),
                encoding="utf-8",
            )

            report = build_citation_quality_gate(root, quality_mode="claim_safe")

        self.assertEqual(report["status"], "fail")
        self.assertIn("critical_unknown_reference", report["hard_gate_failures"])
        self.assertIn("citation_duplicate_support", report["warning_codes"])
        self.assertIn("citation_bomb_detected", report["warning_codes"])

    def test_missing_support_evidence_for_critical_need_fails_claim_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root, cite_key="Known", title="Known Title")
            _write_claim_map(root, [{"id": "C1", "claim_type": "novelty", "required": True, "citation_required": True, "citation_keys": ["Known"]}])

            report = build_citation_quality_gate(root, quality_mode="claim_safe")

        self.assertEqual(report["status"], "fail")
        self.assertIn("critical_citation_support_missing", report["hard_gate_failures"])

    def test_stale_rendered_reference_audit_fails_claim_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root, cite_key="Known", title="Known Title")
            rendered_path = rendered_reference_audit_path(root)
            payload = json.loads(rendered_path.read_text(encoding="utf-8"))
            payload["manuscript_sha256"] = "0" * 64
            payload["paper_full_tex_sha256"] = "0" * 64
            rendered_path.write_text(json.dumps(payload), encoding="utf-8")

            report = build_citation_quality_gate(root, quality_mode="claim_safe")

        self.assertEqual(report["status"], "fail")
        self.assertIn("citation_quality_stale", report["hard_gate_failures"])

    def test_cli_writes_citation_quality_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root, cite_key="Known", title="Known Title")
            output = root / "citation-quality.json"
            stdout = io.StringIO()
            with _chdir(root), contextlib.redirect_stdout(stdout):
                exit_code = cli_main(["audit-citation-quality", "--quality-mode", "claim_safe", "--output", str(output)])
            payload = json.loads(stdout.getvalue())
            output_exists = output.exists()

        self.assertEqual(exit_code, 0)
        self.assertTrue(output_exists)
        self.assertEqual(payload["report"]["schema_version"], CITATION_QUALITY_GATE_SCHEMA_VERSION)
        self.assertEqual(Path(payload["path"]), output)

    def test_quality_eval_includes_citation_quality_gate_without_raw_leaks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root, cite_key="Known", title="Known Title")
            write_planning_artifacts(root)

            payload = build_quality_eval(root, quality_mode="ralph")
            gate = payload["tiers"]["tier_2_claim_safety"]["checks"]["citation_quality_gate"]
            rendered = json.dumps(gate, ensure_ascii=False)

        self.assertEqual(gate["schema_version"], CITATION_QUALITY_GATE_SCHEMA_VERSION)
        self.assertNotIn("citation_quality_gate", payload["source_artifacts"])
        self.assertIn("citation_quality_gate_sha256", payload["source_artifacts"])
        self.assertNotIn(str(root), rendered)
        self.assertNotIn("Synthetic claim", rendered)
        self.assertNotIn("Known Title", rendered)

    def test_quality_loop_plan_routes_critical_citation_quality_to_machine_work(self) -> None:
        quality_eval = {
            "tiers": {
                "tier_2_claim_safety": {
                    "checks": {
                        "citation_quality_gate": {
                            "status": "fail",
                            "hard_gate_failures": ["critical_unknown_reference", "critical_unsupported_citation"],
                        }
                    },
                    "failing_codes": ["critical_unknown_reference", "critical_unsupported_citation"],
                }
            }
        }

        actions = _quality_eval_actions(quality_eval)
        citation_actions = [action for action in actions if str(action.get("code")) in {"critical_unknown_reference", "critical_unsupported_citation"}]

        self.assertTrue(citation_actions)
        self.assertTrue(all(action.get("automation") in {"automatic", "semi_auto"} for action in citation_actions))
        self.assertFalse(any(action.get("automation") == "human_needed" for action in citation_actions))

    def test_machine_solvable_citation_gap_remains_research_routed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            material = root / "material"
            material.mkdir()
            (material / "idea.md").write_text("We introduce a new synthetic workflow that improves review reliability by 12 percent.\n", encoding="utf-8")
            (material / "experiment_log.md").write_text("Synthetic experiment notes.\n", encoding="utf-8")
            (material / "references.bib").write_text("@article{unknown2026, title={Unknown}, author={Anonymous}, year={TODO}}\n", encoding="utf-8")

            state = run_until_blocked(root, material_path=material)

        self.assertNotEqual(state.facets.interaction, "human_needed")
        self.assertIn(state.next_actions[0].action_type, {"start_autoresearch", "start_autoresearch_goal"})

    def test_default_gate_path_is_session_artifact_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root)
            path = citation_quality_gate_path(root)

        self.assertEqual(path.name, "citation_quality_gate.json")
        self.assertIn(".paper-orchestra", str(path))


if __name__ == "__main__":
    unittest.main()
