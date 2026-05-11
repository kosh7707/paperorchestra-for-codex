from __future__ import annotations

import json
import tempfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from paperorchestra.citation_integrity import (
    build_citation_source_match,
    build_rendered_reference_audit,
    citation_integrity_audit_path,
    citation_integrity_check,
    citation_intent_plan_path,
    citation_source_match_path,
    rendered_reference_audit_path,
    write_rendered_reference_audit,
    write_citation_integrity_audit,
)
from paperorchestra.cli import main as cli_main
from paperorchestra.models import InputBundle
from paperorchestra.session import artifact_path, create_session, load_session, save_session


def _init_session(root: Path):
    for name, content in {
        "idea.md": "# Idea\n",
        "experimental_log.md": "# Log\n",
        "template.tex": "\\documentclass{article}\n\\begin{document}\\end{document}\n",
        "guidelines.md": "Guidelines\n",
    }.items():
        (root / name).write_text(content, encoding="utf-8")
    (root / "figures").mkdir()
    return create_session(
        root,
        InputBundle(
            idea_path=str(root / "idea.md"),
            experimental_log_path=str(root / "experimental_log.md"),
            template_path=str(root / "template.tex"),
            guidelines_path=str(root / "guidelines.md"),
            figures_dir=str(root / "figures"),
            cutoff_date="2024-11-01",
        ),
    )


def _bib_entry(key: str, *, title: str | None = None, author: str | None = "Alice", year: str | None = "2024") -> str:
    fields = []
    if title is not None:
        fields.append(f"  title = {{{title}}}")
    if author is not None:
        fields.append(f"  author = {{{author}}}")
    if year is not None:
        fields.append(f"  year = {{{year}}}")
    return "@article{" + key + ",\n" + ",\n".join(fields) + "\n}\n"


def test_rendered_reference_audit_uses_visible_subset_not_total_bib_entries() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        state = _init_session(root)
        visible = [f"Ref{i:02d}" for i in range(1, 50)]
        unused = [f"Unused{i:02d}" for i in range(1, 12)]
        paper = artifact_path(root, "paper.full.tex")
        paper.write_text("\\cite{" + ",".join(visible) + "}\n", encoding="utf-8")
        refs = artifact_path(root, "references.bib")
        refs.write_text("\n".join(_bib_entry(key, title=f"Title {key}") for key in [*visible, *unused]), encoding="utf-8")
        bbl = artifact_path(root, "paper.full.bbl")
        bbl.write_text("\n".join(f"\\bibitem{{{key}}} Rendered {key}." for key in visible), encoding="utf-8")
        state.artifacts.paper_full_tex = str(paper)
        state.artifacts.references_bib = str(refs)
        save_session(root, state)

        audit = build_rendered_reference_audit(root)

        assert audit["status"] == "pass"
        assert audit["denominator_source"] == "bbl_bibitems"
        assert audit["visible_reference_count"] == 49
        assert audit["bib_entry_count"] == 60
        assert audit["cited_key_count"] == 49
        assert len(audit["unused_bib_keys"]) == 11
        assert "rendered_reference_unknown_metadata" not in audit["failing_codes"]


def test_rendered_reference_audit_fails_unknown_visible_metadata_and_missing_bib_key() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        state = _init_session(root)
        paper = artifact_path(root, "paper.full.tex")
        paper.write_text("\\cite{Known,UnknownMeta,MissingBib}\n", encoding="utf-8")
        refs = artifact_path(root, "references.bib")
        refs.write_text(_bib_entry("Known", title="Known Title") + _bib_entry("UnknownMeta", title="Unknown", author="Unknown", year="Unknown"), encoding="utf-8")
        bbl = artifact_path(root, "paper.full.bbl")
        bbl.write_text("\\bibitem{Known} Known.\n\\bibitem{UnknownMeta} Unknown.\n\\bibitem{MissingBib} Missing.\n", encoding="utf-8")
        state.artifacts.paper_full_tex = str(paper)
        state.artifacts.references_bib = str(refs)
        save_session(root, state)

        audit = build_rendered_reference_audit(root)

        assert audit["status"] == "fail"
        assert "UnknownMeta" in audit["unknown_metadata_keys"]
        assert "MissingBib" in audit["missing_bib_keys_for_cites"]
        assert "rendered_reference_unknown_metadata" in audit["failing_codes"]
        assert "rendered_reference_missing_bib_key" in audit["failing_codes"]


def test_rendered_reference_tex_fallback_fails_claim_safe_denominator_visibility() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        state = _init_session(root)
        paper = artifact_path(root, "paper.full.tex")
        paper.write_text("\\cite{Known}\n", encoding="utf-8")
        refs = artifact_path(root, "references.bib")
        refs.write_text(_bib_entry("Known", title="Known Title"), encoding="utf-8")
        state.artifacts.paper_full_tex = str(paper)
        state.artifacts.references_bib = str(refs)
        save_session(root, state)

        audit = build_rendered_reference_audit(root, quality_mode="claim_safe")

        assert audit["denominator_source"] == "tex_cited_keys_fallback"
        assert "rendered_reference_denominator_not_visible" in audit["failing_codes"]
        assert audit["status"] == "fail"


def test_rendered_reference_audit_failing_codes_propagate_to_citation_integrity_check() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        state = _init_session(root)
        paper = artifact_path(root, "paper.full.tex")
        paper.write_text("\\cite{Known}\n", encoding="utf-8")
        state.artifacts.paper_full_tex = str(paper)
        save_session(root, state)
        write_rendered_reference_audit(root, quality_mode="claim_safe")

        result = citation_integrity_check(root, load_session(root), quality_mode="claim_safe")

        assert "rendered_reference_denominator_not_visible" in result["failing_codes"]


def test_citation_semantics_detects_bombs_duplicates_and_claim_source_mismatch() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        state = _init_session(root)
        paper = artifact_path(root, "paper.full.tex")
        paper.write_text(
            "Bomb~\\cite{A,B,C,D}.\n"
            "Repeat one~\\cite{R}. Repeat two~\\cite{R}. Repeat three~\\cite{R}. Repeat four~\\cite{R}.\n",
            encoding="utf-8",
        )
        state.artifacts.paper_full_tex = str(paper)
        save_session(root, state)
        review = paper.parent / "citation_support_review.json"
        review.write_text(
            json.dumps(
                {
                    "items": [
                        {"id": "1", "sentence": "Unsupported~\\cite{A}.", "citation_keys": ["A"], "support_status": "metadata_only"},
                        *[
                            {"id": f"r{i}", "sentence": f"Repeat {i}~\\cite{{R}}.", "citation_keys": ["R"], "support_status": "supported"}
                            for i in range(1, 5)
                        ],
                    ]
                }
            ),
            encoding="utf-8",
        )

        _, audit = write_citation_integrity_audit(root, quality_mode="claim_safe")

        assert audit["status"] == "fail"
        assert "citation_bomb_detected" in audit["failing_codes"]
        assert "citation_duplicate_support" in audit["failing_codes"]
        assert "claim_source_mismatch" in audit["failing_codes"]


def test_citation_semantics_positive_roles_and_context_policy_pass() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        state = _init_session(root)
        paper = artifact_path(root, "paper.full.tex")
        paper.write_text(
            "Normal~\\cite{A,B}. Background~\\cite{Survey}. "
            "Repeat method~\\cite{R}. Repeat benchmark~\\cite{R}. Repeat limitation~\\cite{R}. Repeat positioning~\\cite{R}.\n",
            encoding="utf-8",
        )
        claim_map = artifact_path(root, "claim_map.json")
        claim_map.write_text(
            json.dumps(
                {
                    "claims": [
                        {"id": "own-method", "claim_type": "method", "grounding": "source_material", "required": True, "citation_keys": []},
                        {"id": "bg", "claim_type": "positioning", "required": True, "citation_required": True, "citation_keys": ["Survey"]},
                    ]
                }
            ),
            encoding="utf-8",
        )
        placement = artifact_path(root, "citation_placement_plan.json")
        placement.write_text(
            json.dumps(
                {
                    "placements": [
                        {"citation_key": "R", "claim_id": "m", "citation_role": "method"},
                        {"citation_key": "R", "claim_id": "b", "citation_role": "benchmark"},
                        {"citation_key": "R", "claim_id": "l", "citation_role": "limitation"},
                        {"citation_key": "R", "claim_id": "p", "citation_role": "positioning"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        state.artifacts.paper_full_tex = str(paper)
        state.artifacts.claim_map_json = str(claim_map)
        state.artifacts.citation_placement_plan_json = str(placement)
        save_session(root, state)
        review = paper.parent / "citation_support_review.json"
        review.write_text(
            json.dumps(
                {
                    "items": [
                        {"id": "n", "sentence": "Normal~\\cite{A,B}.", "citation_keys": ["A", "B"], "support_status": "supported"},
                        *[
                            {"id": f"r{i}", "sentence": f"Repeat {i}~\\cite{{R}}.", "citation_keys": ["R"], "support_status": "supported", "claim_id": cid, "citation_role": role}
                            for i, (cid, role) in enumerate([("m", "method"), ("b", "benchmark"), ("l", "limitation"), ("p", "positioning")], start=1)
                        ],
                    ]
                }
            ),
            encoding="utf-8",
        )

        _, audit = write_citation_integrity_audit(root, quality_mode="claim_safe")

        assert "citation_bomb_detected" not in audit["failing_codes"]
        assert "citation_duplicate_support" not in audit["failing_codes"]
        assert "claim_source_mismatch" not in audit["failing_codes"]
        assert "citation_context_policy_violation" not in audit["failing_codes"]


def test_citation_semantics_context_policy_catches_future_own_contribution_citations() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        state = _init_session(root)
        paper = artifact_path(root, "paper.full.tex")
        paper.write_text("Own contribution~\\cite{External}.\n", encoding="utf-8")
        claim_map = artifact_path(root, "claim_map.json")
        claim_map.write_text(json.dumps({"claims": [{"id": "own", "claim_type": "own_contribution", "citation_keys": ["External"]}]}), encoding="utf-8")
        state.artifacts.paper_full_tex = str(paper)
        state.artifacts.claim_map_json = str(claim_map)
        save_session(root, state)

        _, audit = write_citation_integrity_audit(root, quality_mode="claim_safe")

        assert "citation_context_policy_violation" in audit["failing_codes"]


def test_cli_citation_audits_write_session_default_intent_source_match_and_integrity_artifacts() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        state = _init_session(root)
        paper = artifact_path(root, "paper.full.tex")
        paper.write_text(
            "\\section{Intro}\n"
            "Prior schedulers motivate this design~\\cite{Prior}.\n",
            encoding="utf-8",
        )
        refs = artifact_path(root, "references.bib")
        refs.write_text(_bib_entry("Prior", title="Prior Scheduler"), encoding="utf-8")
        artifact_path(root, "paper.full.bbl").write_text("\\bibitem{Prior} Prior Scheduler.\n", encoding="utf-8")
        claim_map = artifact_path(root, "claim_map.json")
        claim_map.write_text(
            json.dumps(
                {
                    "claims": [
                        {
                            "id": "c1",
                            "claim_type": "background",
                            "citation_keys": ["Prior"],
                            "required_source_type": "prior_work",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        support = paper.parent / "citation_support_review.json"
        support.write_text(
            json.dumps(
                {
                    "evidence_mode": "web",
                    "items": [
                        {
                            "id": "s1",
                            "sentence": "Prior schedulers motivate this design~\\cite{Prior}.",
                            "citation_keys": ["Prior"],
                            "support_status": "supported",
                            "claim_type": "background",
                            "evidence": [{"url": "https://example.test/prior"}],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        state.artifacts.paper_full_tex = str(paper)
        state.artifacts.references_bib = str(refs)
        state.artifacts.claim_map_json = str(claim_map)
        save_session(root, state)

        with patch("os.getcwd", return_value=str(root)), redirect_stdout(StringIO()):
            assert cli_main(["audit-rendered-references", "--quality-mode", "claim_safe"]) == 0
            assert cli_main(["audit-citation-integrity", "--quality-mode", "claim_safe"]) == 0

        assert rendered_reference_audit_path(root).exists()
        assert citation_intent_plan_path(root).exists()
        assert citation_source_match_path(root).exists()
        assert citation_integrity_audit_path(root).exists()
        integrity = json.loads(citation_integrity_audit_path(root).read_text(encoding="utf-8"))
        assert integrity["source_artifacts"]["citation_intent_plan_sha256"]
        assert integrity["source_artifacts"]["citation_source_match_sha256"]
        intent = json.loads(citation_intent_plan_path(root).read_text(encoding="utf-8"))
        assert intent["items"][0]["claim_ids"] == ["c1"]
        source_match = json.loads(citation_source_match_path(root).read_text(encoding="utf-8"))
        assert source_match["status"] == "pass"
        assert source_match["support_status_counts"] == {"supported": 1}


def test_citation_source_match_degrades_when_support_review_missing() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        state = _init_session(root)
        paper = artifact_path(root, "paper.full.tex")
        paper.write_text("Background~\\cite{Prior}.\n", encoding="utf-8")
        state.artifacts.paper_full_tex = str(paper)
        save_session(root, state)

        source_match = build_citation_source_match(root, quality_mode="claim_safe")

        assert source_match["status"] == "skipped"
        assert source_match["reason"] == "citation_support_review_missing_or_unreadable"
