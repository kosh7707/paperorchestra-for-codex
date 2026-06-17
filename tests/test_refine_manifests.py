from __future__ import annotations

from paperorchestra.engine import refine_manifests, refine_stages


def test_refine_stages_facade_reexports_manifest_helpers() -> None:
    assert (
        refine_stages.record_accepted_refinement_lane_manifest
        is refine_manifests.record_accepted_refinement_lane_manifest
    )
    assert (
        refine_stages.record_rejected_refinement_lane_manifest
        is refine_manifests.record_rejected_refinement_lane_manifest
    )


def test_refinement_lane_manifest_kwargs_names_accept_and_reject_records() -> None:
    accepted = refine_manifests.refinement_lane_manifest_kwargs(
        runtime_mode="omx_native",
        lane_type="refiner",
        owner="codex",
        fallback_used=False,
        accepted=True,
        compile_blocked=False,
        input_artifacts=["paper.tex", "review.json"],
        output_artifacts=["paper.full.tex", "worklog.json", "validation.json"],
        notes=["ok"],
    )
    accepted_fallback = refine_manifests.refinement_lane_manifest_kwargs(
        runtime_mode="compatibility",
        lane_type="mock",
        owner="local",
        fallback_used=True,
        accepted=True,
        compile_blocked=False,
        input_artifacts=["paper.tex", ""],
        output_artifacts=["paper.full.tex", "worklog.json", "validation.json"],
        notes=["fallback"],
    )
    rejected = refine_manifests.refinement_lane_manifest_kwargs(
        runtime_mode="compatibility",
        lane_type="mock",
        owner="local",
        fallback_used=True,
        accepted=False,
        compile_blocked=True,
        input_artifacts=["paper.tex", ""],
        output_artifacts=["worklog.json", "validation.json"],
        notes=["blocked"],
    )

    assert accepted == {
        "stage": "refinement",
        "role": "Content Refinement Agent",
        "runtime_mode": "omx_native",
        "lane_type": "refiner",
        "owner": "codex",
        "status": "completed",
        "input_artifacts": ["paper.tex", "review.json"],
        "output_artifacts": ["paper.full.tex", "worklog.json", "validation.json"],
        "fallback_used": False,
        "notes": ["ok"],
    }
    assert accepted_fallback["status"] == "fallback_completed"
    assert rejected["status"] == "blocked"
    assert rejected["fallback_used"] is True
    assert rejected["output_artifacts"] == ["worklog.json", "validation.json"]
