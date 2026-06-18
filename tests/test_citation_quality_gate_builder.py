from __future__ import annotations

from pathlib import Path

from paperorchestra.core.io import write_json
from paperorchestra.core.models import InputBundle
from paperorchestra.core.session import artifact_path, create_session, save_session
from paperorchestra.loop_engine.quality.utils import _file_sha256
from paperorchestra.reviews.citation_integrity import citation_integrity_audit_path, citation_source_match_path, rendered_reference_audit_path
from paperorchestra.reviews.citation_quality import build_citation_quality_gate_internal


def _session(tmp_path: Path):
    for name, content in {
        "idea.md": "idea",
        "experimental_log.md": "experiment",
        "template.tex": "template",
        "guidelines.md": "guidelines",
    }.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    return create_session(
        tmp_path,
        InputBundle(
            idea_path=str(tmp_path / "idea.md"),
            experimental_log_path=str(tmp_path / "experimental_log.md"),
            template_path=str(tmp_path / "template.tex"),
            guidelines_path=str(tmp_path / "guidelines.md"),
        ),
    )


def test_citation_quality_gate_reports_missing_manuscript(tmp_path: Path) -> None:
    _session(tmp_path)

    payload = build_citation_quality_gate_internal(tmp_path, quality_mode="claim_safe")

    assert payload["status"] == "fail"
    assert payload["hard_gate_failures"] == ["citation_quality_manuscript_missing"]
    assert payload["public_report"]["failures"] == [
        {
            "case": "",
            "key": "",
            "code": "citation_quality_manuscript_missing",
            "message": "The manuscript is missing for citation quality evaluation.",
        }
    ]


def test_citation_quality_gate_flags_claim_safe_unknown_reference(tmp_path: Path) -> None:
    state = _session(tmp_path)
    paper = artifact_path(tmp_path, "paper.full.tex")
    paper.write_text(r"Evidence is required here \\cite{MissingKey}.", encoding="utf-8")
    state.artifacts.paper_full_tex = str(paper)
    state.artifacts.claim_map_json = str(artifact_path(tmp_path, "claim-map.json"))
    state.artifacts.citation_placement_plan_json = str(artifact_path(tmp_path, "citation-placement-plan.json"))
    save_session(tmp_path, state)
    manuscript_sha = _file_sha256(paper)

    write_json(
        rendered_reference_audit_path(tmp_path),
        {
            "manuscript_sha256": manuscript_sha,
            "unknown_metadata_keys": ["MissingKey"],
            "missing_bib_keys_for_cites": [],
            "weak_identity_keys": [],
            "visible_reference_keys": ["MissingKey"],
        },
    )
    write_json(
        paper.parent / "citation_support_review.json",
        {
            "items": [
                {
                    "id": "support-1",
                    "case_id": "case-1",
                    "citation_keys": ["MissingKey"],
                    "support_status": "supported",
                    "critical": True,
                }
            ]
        },
    )
    write_json(citation_source_match_path(tmp_path), {"manuscript_sha256": manuscript_sha, "status": "pass"})
    write_json(citation_integrity_audit_path(tmp_path), {"manuscript_sha256": manuscript_sha, "status": "pass"})
    write_json(state.artifacts.claim_map_json, {"claims": []})
    write_json(state.artifacts.citation_placement_plan_json, {"placements": []})

    payload = build_citation_quality_gate_internal(tmp_path, quality_mode="claim_safe")

    assert payload["status"] == "fail"
    assert payload["hard_gate_failures"] == ["critical_unknown_reference"]
    assert payload["counts"]["critical_need_count"] == 1
    assert payload["items"][0]["support_status"] == "supported"
    assert payload["items"][0]["metadata_status"] == "unknown"
    assert payload["public_report"]["failures"][0]["code"] == "critical_unknown_reference"
