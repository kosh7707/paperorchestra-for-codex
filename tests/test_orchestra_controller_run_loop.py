from __future__ import annotations

from pathlib import Path

from paperorchestra.orchestra.controller import run_until_blocked


def test_run_until_blocked_builds_reference_claim_and_research_evidence(tmp_path: Path) -> None:
    material = tmp_path / "materials"
    material.mkdir()
    (material / "idea.md").write_text(
        "We introduce a novel system because it reduces false positives by 25 percent. "
        "The method supports evidence grounded alert triage for Java SAST alerts.\n",
        encoding="utf-8",
    )
    (material / "refs.bib").write_text(
        "@inproceedings{Known2024, title={Known Paper}, author={Alice and Bob}, year={2024}, booktitle={Conf}}\n",
        encoding="utf-8",
    )

    state = run_until_blocked(tmp_path, material_path=material)

    assert state.facets.material == "inventoried_sufficient"
    assert state.facets.source_digest == "ready"
    assert state.facets.claims == "candidate"
    assert state.facets.evidence == "research_needed"
    assert [item["kind"] for item in state.evidence_refs] == [
        "material_inventory",
        "source_digest",
        "reference_metadata_audit",
        "claim_graph",
        "evidence_research_mission",
        "omx_invocation_evidence",
    ]
    assert [(action.action_type, action.reason) for action in state.next_actions] == [("start_autoresearch", "research_needed")]
